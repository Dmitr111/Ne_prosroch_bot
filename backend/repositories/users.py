"""Репозиторий пользователей.

Пользователь заводится при первом обращении к mini app, отдельной
регистрации нет. Планировщику нужен перечень тех, кого обходить
при ежедневной проверке сроков годности.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import User


class UserRepository:
    """Запросы к пользователям."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_ids(self) -> list[int]:
        """Идентификаторы всех пользователей в порядке регистрации."""
        statement = select(User.telegram_id).order_by(User.created_at, User.telegram_id)
        return list((await self._session.scalars(statement)).all())

    async def get_or_create(self, telegram_id: int, username: str | None) -> User:
        """Пользователь по Telegram-идентификатору, при отсутствии — новый.

        Отдельной регистрации в приложении нет: запись заводится при первом
        обращении к mini app. Имя пользователя обновляется, если оно
        изменилось в Telegram.
        """
        user = await self._session.get(User, telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, username=username)
            self._session.add(user)
            await self._session.flush()
            await self._session.refresh(user)
            return user

        if username is not None and user.username != username:
            user.username = username
            await self._session.flush()
        return user
