"""Тесты запросов репозитория продуктов.

Сессия подставная и только запоминает выражение: проверяется не результат
выборки, а сам SQL — что выборки ограничены статусом «в наличии».

Смысл проверки в разграничении статусов. Позиция со статусом removed
удалена пользователем из перечня, written_off — реальные пищевые потери.
Если фильтр когда-нибудь перепишут «от обратного» (всё, кроме списанного),
удалённые продукты молча вернутся и в подбор, и в напоминания, а тесты
на подставных репозиториях этого не заметят.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from backend.repositories.products import ProductRepository

TODAY = date(2026, 3, 10)


class FakeResult:
    def all(self) -> list[Any]:
        return []

    @property
    def rowcount(self) -> int:
        return 0


class CapturingSession:
    """Запоминает выражения вместо обращения к БД."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def scalars(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult()

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult()


def rendered(statement: Any) -> str:
    """SQL с подставленными значениями."""
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.asyncio
async def test_get_active_selects_only_in_stock() -> None:
    """В подбор рецептов идут только продукты в наличии."""
    session = CapturingSession()

    await ProductRepository(session).get_active(1)

    sql = rendered(session.statements[0])
    assert "products.status_code = 'in_stock'" in sql
    assert "removed" not in sql


@pytest.mark.asyncio
async def test_get_expiring_selects_only_in_stock() -> None:
    """В рассылку напоминаний тоже только то, что в наличии."""
    session = CapturingSession()

    await ProductRepository(session).get_expiring(1, threshold_days=3, today=TODAY)

    sql = rendered(session.statements[0])
    assert "products.status_code = 'in_stock'" in sql
    assert "products.expiry_date >= '2026-03-10'" in sql


@pytest.mark.asyncio
async def test_write_off_touches_only_in_stock() -> None:
    """Удалённая позиция не превращается задним числом в списанную.

    Иначе ошибочно внесённые продукты попали бы в статистику пищевых
    потерь третьей главы и завысили её.
    """
    session = CapturingSession()

    await ProductRepository(session).write_off_expired(TODAY)

    sql = rendered(session.statements[0])
    assert "SET status_code='written_off'" in sql.replace(" = ", "=")
    assert "products.status_code = 'in_stock'" in sql


@pytest.mark.asyncio
async def test_get_all_without_status_returns_everything() -> None:
    """Перечень с status=all не фильтрует по статусу."""
    session = CapturingSession()

    await ProductRepository(session).get_all(1, status_code=None)

    # Колонка есть в выборке, но условия по ней нет
    assert "products.status_code =" not in rendered(session.statements[0])


@pytest.mark.asyncio
async def test_get_all_filters_by_given_status() -> None:
    session = CapturingSession()

    await ProductRepository(session).get_all(1, status_code="removed")

    assert "products.status_code = 'removed'" in rendered(session.statements[0])


@pytest.mark.asyncio
async def test_expiring_window_covers_threshold() -> None:
    """Граница окна — сегодня плюс порог, включительно."""
    session = CapturingSession()

    await ProductRepository(session).get_expiring(1, threshold_days=3, today=TODAY)

    sql = rendered(session.statements[0])
    assert f"products.expiry_date <= '{TODAY + timedelta(days=3)}'" in sql
