"""Тесты текста напоминаний и правил повторной отправки.

Проверяется чистая логика: формирование сообщения и суточная пауза.
Telegram и БД не задействованы.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.bot.notifications import NO_RECIPES_TEXT, format_expiry_message
from backend.repositories.notifications import NotificationType
from backend.scheduler.jobs import notification_type, products_to_notify

TODAY = date(2026, 3, 10)
NOW = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize("utc_hour, local_day", [(18, 9), (19, 10)])
async def test_application_date_around_midnight(monkeypatch, utc_hour, local_day) -> None:
    """UTC и дата ОС не сдвигают срочность, подбор и задания относительно друг друга."""
    from backend import clock
    from backend.api import products as products_api
    from backend.config import settings
    from backend.scheduler import jobs
    from tests.test_service import build, product as stock_product, recipe

    moment = datetime(2026, 3, 9, utc_hour, 59, tzinfo=timezone.utc)
    local_date = date(2026, 3, local_day)
    monkeypatch.setattr(settings, "timezone", "Asia/Yekaterinburg")
    frozen_datetime = Mock()
    frozen_datetime.now.side_effect = lambda tz: moment.astimezone(tz)
    monkeypatch.setattr(clock, "datetime", frozen_datetime)
    assert clock.application_now().date() == local_date

    # Прямой вызов обработчика с подставными репозиториями, без HTTP и БД.
    milk = SimpleNamespace(
        id=1, name="Молоко", expiry_date=TODAY, manufacture_date=None,
        ingredient_name="молоко", storage_place_id=None, status_code="in_stock",
        quantity=1, unit="л",
    )
    frozen_datetime.now.reset_mock()
    [item] = await products_api.list_products(
        SimpleNamespace(telegram_id=1),
        SimpleNamespace(get_all=AsyncMock(return_value=[milk])),
        SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(horizon_days=7))),
    )
    assert item.days_left == (TODAY - local_date).days
    frozen_datetime.now.assert_called_once()
    fixture = build([stock_product(1, "молоко", 0)], [recipe("Коктейль", "молоко")])
    [recommendation] = await fixture.service.get_recommendations(1)
    assert recommendation.covered_weight == 7 - item.days_left

    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(jobs, "async_session_factory", Mock(return_value=context))
    recipients = AsyncMock(return_value=[1])
    monkeypatch.setattr(jobs, "SettingsRepository", Mock(
        return_value=SimpleNamespace(get_recipients=recipients)
    ))
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(jobs, "_notify_user", notify)
    bot = Mock()
    frozen_datetime.now.reset_mock()
    assert await jobs.check_expiry_dates(bot) == 1
    frozen_datetime.now.assert_called_once()
    recipients.assert_awaited_once_with((utc_hour + 5) % 24)
    notify.assert_awaited_once_with(bot, 1, local_date, moment)

    write_off = AsyncMock(return_value=1)
    monkeypatch.setattr(jobs, "ProductRepository", Mock(
        return_value=SimpleNamespace(write_off_expired=write_off)
    ))
    frozen_datetime.now.reset_mock()
    assert await jobs.write_off_expired() == 1
    frozen_datetime.now.assert_called_once()
    write_off.assert_awaited_once_with(local_date)
    frozen_datetime.now.reset_mock()
    await jobs.write_off_expired(today=TODAY)
    write_off.assert_awaited_with(TODAY)
    await jobs.check_expiry_dates(bot, now=moment)
    notify.assert_awaited_with(bot, 1, local_date, moment)
    frozen_datetime.now.assert_not_called()


@dataclass
class FakeProduct:
    id: int
    name: str
    expiry_date: date


@dataclass
class FakeRecipe:
    title: str
    cooking_time_min: int | None = None


def product(product_id: int, name: str, days_left: int) -> FakeProduct:
    return FakeProduct(
        id=product_id, name=name, expiry_date=TODAY + timedelta(days=days_left)
    )


# ---------------------------------------------------------------------------
# Текст напоминания
# ---------------------------------------------------------------------------


def test_message_marks_today_red_and_upcoming_yellow() -> None:
    message = format_expiry_message(
        [product(1, "Молоко", 0), product(2, "Творог", 2)],
        [FakeRecipe("Сырники", 25)],
        TODAY,
    )

    assert "🔴 Молоко — сегодня" in message
    assert "🟡 Творог — через 2 дня" in message
    assert "• Сырники — 25 мин" in message


def test_message_without_recipes_still_informs() -> None:
    """Пустой набор рецептов не отменяет напоминание."""
    message = format_expiry_message([product(1, "Молоко", 1)], [], TODAY)

    assert "Молоко" in message
    assert NO_RECIPES_TEXT in message


def test_recipe_without_cooking_time() -> None:
    message = format_expiry_message(
        [product(1, "Молоко", 1)], [FakeRecipe("Коктейль", None)], TODAY
    )

    assert "• Коктейль" in message
    assert "мин" not in message


def test_day_forms() -> None:
    """Окончания числительных: день, дня, дней."""
    products = [
        product(1, "Сегодня", 0),
        product(2, "Завтра", 1),
        product(3, "Двое", 2),
        product(4, "Пятеро", 5),
        product(5, "Одиннадцать", 11),
        product(6, "Двадцать один", 21),
    ]

    message = format_expiry_message(products, [], TODAY)

    assert "Сегодня — сегодня" in message
    assert "Завтра — завтра" in message
    assert "Двое — через 2 дня" in message
    assert "Пятеро — через 5 дней" in message
    assert "Одиннадцать — через 11 дней" in message
    assert "Двадцать один — через 21 день" in message


def test_expired_product_is_marked_red() -> None:
    """Просроченное в рассылку обычно не попадает, но помечается красным."""
    message = format_expiry_message([product(1, "Кефир", -1)], [], TODAY)

    assert message.startswith("Скоро истекает срок годности:")
    assert "🔴 Кефир" in message


# ---------------------------------------------------------------------------
# Суточная пауза
# ---------------------------------------------------------------------------


def test_product_notified_today_is_skipped() -> None:
    """О продукте, про который сообщали час назад, повторно не пишем."""
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(hours=1)}

    assert products_to_notify([milk], last_notified, NOW) == []


def test_product_notified_yesterday_is_repeated() -> None:
    """Циклический таймер R/P1D: через сутки напоминание повторяется."""
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(days=1, minutes=1)}

    assert products_to_notify([milk], last_notified, NOW) == [milk]


def test_period_tolerates_hourly_run_drift() -> None:
    """Почти сутки — уже повод напомнить снова.

    Задача стартует в начале часа, а отметка в журнале ставится на
    секунды позже. Назавтра в тот же час проходит 23:59:5x, и при паузе
    ровно в сутки напоминание срывалось бы каждый день.
    """
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(hours=23, minutes=59, seconds=57)}

    assert products_to_notify([milk], last_notified, NOW) == [milk]


def test_product_notified_hours_ago_is_still_skipped() -> None:
    """Внутри суток повторов нет: 12 часов — рано."""
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(hours=12)}

    assert products_to_notify([milk], last_notified, NOW) == []


def test_product_never_notified_is_selected() -> None:
    milk = product(1, "Молоко", 1)

    assert products_to_notify([milk], {}, NOW) == [milk]


def test_only_fresh_products_are_selected() -> None:
    """Из смешанного перечня остаются только те, о ком пора напомнить."""
    milk = product(1, "Молоко", 1)
    curd = product(2, "Творог", 2)
    bread = product(3, "Хлеб", 0)
    last_notified = {1: NOW - timedelta(hours=2), 2: NOW - timedelta(days=3)}

    selected = products_to_notify([milk, curd, bread], last_notified, NOW)

    assert [item.name for item in selected] == ["Творог", "Хлеб"]


# ---------------------------------------------------------------------------
# Вид напоминания
# ---------------------------------------------------------------------------


def test_type_is_expiry_for_new_product() -> None:
    assert notification_type([product(1, "Молоко", 1)], {}) == NotificationType.EXPIRY


def test_type_is_repeat_when_all_products_known() -> None:
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(days=2)}

    assert notification_type([milk], last_notified) == NotificationType.REPEAT


def test_type_is_expiry_when_at_least_one_product_is_new() -> None:
    """Появился новый продукт — напоминание считается первичным."""
    milk = product(1, "Молоко", 1)
    bread = product(2, "Хлеб", 0)
    last_notified = {1: NOW - timedelta(days=2)}

    assert notification_type([milk, bread], last_notified) == NotificationType.EXPIRY
