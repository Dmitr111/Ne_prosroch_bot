"""Репозиторий пользовательских настроек.

Чтение настроек с подстановкой значений по умолчанию, их обновление и
выборка пользователей, которым пора отправить напоминание.
"""

from sqlalchemy import Time, extract, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import DEFAULT_NOTIFY_TIME, User, UserSettings


class SettingsRepository:
    """Запросы к параметрам напоминаний и подбора."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, telegram_id: int) -> UserSettings:
        """Настройки пользователя, при отсутствии — созданные по умолчанию.

        Отдельного шага настройки в приложении нет: запись заводится при
        первом обращении со значениями из схемы (T = 7 дней, k = 5).
        После ``flush`` нужен ``refresh``: значения проставлены на стороне
        СУБД через DEFAULT, и до перечитывания Python о них не знает,
        а неявная догрузка атрибута в асинхронной сессии упала бы.
        """
        settings = await self._session.get(UserSettings, telegram_id)
        if settings is not None:
            return settings

        settings = UserSettings(telegram_id=telegram_id)
        self._session.add(settings)
        await self._session.flush()
        await self._session.refresh(settings)
        return settings

    async def update(self, settings: UserSettings, fields: dict) -> UserSettings:
        """Меняет переданные параметры напоминаний и подбора."""
        for name, value in fields.items():
            setattr(settings, name, value)
        await self._session.flush()
        return settings

    async def get_recipients(self, hour: int) -> list[int]:
        """Пользователи, которым пора отправить напоминание в этот час.

        Время напоминания персональное — из ``notify_time``, поэтому задача
        рассылки запускается ежечасно и на каждом запуске берёт тех, у кого
        час совпал с текущим. Часовой пояс пока общий, из настроек
        приложения: в user_settings своего пояса нет.

        LEFT JOIN и COALESCE нужны для пользователей, у которых строки
        настроек ещё нет: она заводится при первом обращении, а напоминания
        такой пользователь должен получать сразу, во время по умолчанию.
        """
        notify_time = func.coalesce(
            UserSettings.notify_time, literal(DEFAULT_NOTIFY_TIME, Time)
        )
        statement = (
            select(User.telegram_id)
            .outerjoin(UserSettings, UserSettings.telegram_id == User.telegram_id)
            .where(extract("hour", notify_time) == hour)
            .order_by(User.telegram_id)
        )
        return list((await self._session.scalars(statement)).all())
