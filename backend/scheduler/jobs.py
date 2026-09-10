"""Задачи APScheduler.

Ежедневная проверка сроков годности: обход пользователей с включёнными
напоминаниями, расчёт рекомендаций и постановка уведомлений на отправку.

Две задачи с разным расписанием:

* ``check_expiry_dates`` — ежечасно в начале часа. Берёт пользователей,
  у которых ``notify_time`` приходится на текущий час, пересчитывает
  остаточные сроки, отбирает продукты с τ ≤ threshold_days, подбирает
  рецепты и отправляет напоминание. Время напоминания задаёт пользователь,
  ``DAILY_CHECK_TIME`` к нему отношения не имеет;
* ``write_off_expired`` — раз в сутки в ``DAILY_CHECK_TIME``, автоматическое
  списание просроченного: тот самый прерывающий таймер из модели процесса.

Задачи независимы: ``get_expiring`` не возвращает просроченное, поэтому
порядок их выполнения на результат не влияет.

Планировщик поднимается внутри процесса FastAPI (см. ``backend/main.py``),
отдельной очереди задач в проекте нет.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.bot.notifications import send_expiry_notification
from backend.config import settings
from backend.core.service import RecommendationService, RecommendationTrigger
from backend.db.session import async_session_factory
from backend.repositories.notifications import NotificationRepository, NotificationType
from backend.repositories.products import ProductRepository
from backend.repositories.recipes import RecipeRepository
from backend.repositories.recommendations import RecommendationRepository
from backend.repositories.settings import SettingsRepository

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

# Пауза между напоминаниями об одном и том же продукте: циклический
# таймер R/P1D из модели процесса.
#
# Ровно суток здесь быть не может. Задача запускается в начале часа, а
# отметка в журнале ставится на несколько секунд позже, поэтому назавтра
# в тот же час прошло бы 23:59:5x — чуть меньше суток, и напоминание
# сорвалось бы до следующего дня, и так каждый раз. Часовой запас снимает
# этот дрейф, при этом дважды за сутки напоминание не уйдёт: пользователь
# попадает в рассылку один раз в день, в свой notify_time
NOTIFICATION_PERIOD = timedelta(hours=23)


class NotifiableProduct(Protocol):
    """Что нужно от продукта задачам планировщика."""

    id: int
    name: str
    expiry_date: date


def products_to_notify(
    products: Sequence[NotifiableProduct],
    last_notified: Mapping[int, datetime],
    now: datetime,
    period: timedelta = NOTIFICATION_PERIOD,
) -> list[NotifiableProduct]:
    """Отбирает продукты, о которых можно напомнить прямо сейчас.

    Продукт отсеивается, если о нём уже сообщали меньше суток назад:
    повторное напоминание допускается, но не чаще раза в период.
    """
    selected = []
    for product in products:
        sent_at = last_notified.get(product.id)
        if sent_at is not None and now - sent_at < period:
            continue
        selected.append(product)
    return selected


def notification_type(
    products: Sequence[NotifiableProduct], last_notified: Mapping[int, datetime]
) -> str:
    """Первичное напоминание или повторное.

    Повторным считается только то, где ни одного нового продукта нет:
    появился хотя бы один, о котором ещё не сообщали, — напоминание
    первичное.
    """
    if products and all(product.id in last_notified for product in products):
        return NotificationType.REPEAT
    return NotificationType.EXPIRY


async def check_expiry_dates(bot: "Bot", now: datetime | None = None) -> int:
    """Почасовая проверка сроков годности.

    Обходятся только пользователи, у которых ``notify_time`` приходится
    на текущий час: время напоминания персональное. Для каждого — продукты
    с τ ≤ threshold_days, отсев тех, о которых напоминали меньше суток
    назад, подбор рецептов с источником запуска ``by_expiry`` и отправка.
    Пустой набор рецептов отправку не отменяет — информирование происходит
    в любом случае.

    Своя сессия и своя транзакция на каждого пользователя: сбой на одном
    не должен отменять рассылку остальным. Журнал пишется только после
    успешной отправки, иначе напоминание молча потерялось бы.

    :param now: момент запуска; по умолчанию текущее время в часовом поясе
        приложения. Дата и час получателей считаются по местному времени,
        отметка в журнале — в UTC
    :return: число отправленных напоминаний
    """
    local_zone = ZoneInfo(settings.timezone)
    local_now = (now or datetime.now(tz=local_zone)).astimezone(local_zone)
    today = local_now.date()
    moment = local_now.astimezone(timezone.utc)

    async with async_session_factory() as session:
        telegram_ids = await SettingsRepository(session).get_recipients(local_now.hour)
    if not telegram_ids:
        return 0

    sent = 0
    for telegram_id in telegram_ids:
        try:
            if await _notify_user(bot, telegram_id, today, moment):
                sent += 1
        except Exception:  # noqa: BLE001 — один пользователь не валит обход
            logger.exception("проверка сроков не удалась у %s", telegram_id)
    logger.info(
        "проверка сроков в %s: получателей %s, отправлено %s",
        local_now.strftime("%H:%M"),
        len(telegram_ids),
        sent,
    )
    return sent


async def _notify_user(bot: "Bot", telegram_id: int, today: date, now: datetime) -> bool:
    """Обрабатывает одного пользователя. Возвращает True, если отправлено."""
    async with async_session_factory() as session:
        settings_repository = SettingsRepository(session)
        products_repository = ProductRepository(session)
        notifications_repository = NotificationRepository(session)

        user_settings = await settings_repository.get(telegram_id)
        expiring = await products_repository.get_expiring(
            telegram_id, user_settings.threshold_days, today
        )
        if not expiring:
            return False

        last_notified = await notifications_repository.get_last_notified(telegram_id)
        products = products_to_notify(expiring, last_notified, now)
        if not products:
            # Обо всех этих продуктах уже сообщали за последние сутки
            return False

        service = RecommendationService(
            products=products_repository,
            recipes=RecipeRepository(session),
            settings=settings_repository,
            recommendations=RecommendationRepository(session),
        )
        # Напоминанию нужны только сами рецепты: покрытие показывается
        # в приложении, в тексте сообщения его нет
        recipes = [
            item.recipe
            for item in await service.get_recommendations(
                telegram_id, RecommendationTrigger.BY_EXPIRY, today=today
            )
        ]

        delivered = await send_expiry_notification(
            bot, telegram_id, products, recipes, today
        )
        if not delivered:
            # Сеанс подбора не сохраняем: напоминание не дошло
            await session.rollback()
            return False

        await notifications_repository.save(
            telegram_id=telegram_id,
            sent_at=now,
            notification_type=notification_type(products, last_notified),
            product_ids=[product.id for product in products],
        )
        await session.commit()
        return True


async def write_off_expired(today: date | None = None) -> int:
    """Списывает продукты, срок годности которых уже прошёл.

    Прерывающий таймер из модели процесса: продукт не удаляется, ему
    проставляется статус «списан», процесс по нему завершается.
    Единственная задача, привязанная к ``DAILY_CHECK_TIME``.

    :return: число списанных позиций
    """
    today = today or date.today()
    async with async_session_factory() as session:
        written_off = await ProductRepository(session).write_off_expired(today)
        await session.commit()
    if written_off:
        logger.info("списано просроченных продуктов: %s", written_off)
    return written_off


def create_scheduler(bot: "Bot") -> AsyncIOScheduler:
    """Собирает планировщик с задачами рассылки и списания.

    Часовой пояс общий, из ``timezone``: и час напоминания, и время
    списания считаются по местному времени, а не по UTC.
    """
    local_zone = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(timezone=local_zone)

    # Списание — раз в сутки в DAILY_CHECK_TIME
    scheduler.add_job(
        write_off_expired,
        trigger=CronTrigger(
            hour=settings.daily_check_time.hour,
            minute=settings.daily_check_time.minute,
            timezone=local_zone,
        ),
        id="write_off_expired",
        name="Списать просроченные продукты",
        replace_existing=True,
    )
    # Рассылка — ежечасно в начале часа: время напоминания у каждого своё,
    # отбор получателей идёт по notify_time внутри задачи
    scheduler.add_job(
        check_expiry_dates,
        trigger=CronTrigger(minute=0, timezone=local_zone),
        args=[bot],
        id="check_expiry_dates",
        name="Проверить срок годности",
        replace_existing=True,
    )
    return scheduler
