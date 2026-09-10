"""Асинхронный движок SQLAlchemy и фабрика сессий.

Создаёт async engine по DATABASE_URL, async_sessionmaker и зависимость
для получения сессии в обработчиках FastAPI.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    # Проверять соединение перед выдачей из пула: локальная БД в контейнере
    # может быть перезапущена между обращениями
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия БД на время обработки запроса.

    Одна транзакция на запрос: успешно обработали — фиксируем, возникло
    исключение — откатываем. Обработчикам не приходится помнить про
    commit, а частично применённых изменений при ошибке не остаётся.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
