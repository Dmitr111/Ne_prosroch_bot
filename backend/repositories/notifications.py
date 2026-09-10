"""Репозиторий журнала уведомлений.

Хранит факт отправки напоминания и его состав. По журналу планировщик
определяет, о каких продуктах пользователю уже сообщали, чтобы не слать
повторное уведомление о том же продукте чаще раза в сутки.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Notification, NotificationItem


class NotificationType:
    """Вид напоминания, записывается в notifications.type."""

    # Первое сообщение о продукте с истекающим сроком
    EXPIRY = "expiry"
    # Повторное напоминание циклического таймера R/P1D
    REPEAT = "repeat"


class NotificationRepository:
    """Запросы к журналу отправленных напоминаний."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_notified(self, telegram_id: int) -> dict[int, datetime]:
        """Когда о каждом продукте пользователя сообщали в последний раз.

        Одного запроса хватает и для фильтра суточной паузы, и для выбора
        вида напоминания: продукт, которого нет в словаре, ещё ни разу
        не попадал в рассылку.
        """
        statement = (
            select(NotificationItem.product_id, func.max(Notification.sent_at))
            .join(Notification, Notification.id == NotificationItem.notification_id)
            .where(Notification.telegram_id == telegram_id)
            .group_by(NotificationItem.product_id)
        )
        rows = await self._session.execute(statement)
        return {product_id: sent_at for product_id, sent_at in rows}

    async def save(
        self,
        telegram_id: int,
        sent_at: datetime,
        notification_type: str,
        product_ids: Sequence[int],
    ) -> Notification:
        """Записывает отправленное напоминание вместе с его составом.

        Момент отправки передаётся аргументом, а не берётся из ``now()``
        в СУБД: ``now()`` возвращает время начала транзакции и одинаков для
        всех записей внутри неё, а на паре (telegram_id, sent_at) стоит
        UNIQUE — два напоминания в одной транзакции столкнулись бы.

        Принадлежность продуктов владельцу уведомления обеспечивает
        вызывающий код: составного внешнего ключа на products в схеме нет.
        """
        notification = Notification(
            telegram_id=telegram_id,
            sent_at=sent_at,
            type=notification_type,
        )
        self._session.add(notification)
        await self._session.flush()

        for product_id in product_ids:
            self._session.add(
                NotificationItem(
                    notification_id=notification.id, product_id=product_id
                )
            )
        await self._session.flush()

        return notification
