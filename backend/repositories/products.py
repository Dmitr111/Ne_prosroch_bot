"""Репозиторий продуктов.

CRUD-запросы к продуктам пользователя и выборки для алгоритма: активные
продукты, продукты с истекающим сроком годности, списание количества.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Product, ProductStatusCode


class DuplicateProductError(Exception):
    """Позиция с такими владельцем, наименованием и сроком уже заведена.

    Соответствует UNIQUE(telegram_id, name, expiry_date): одинаковые
    продукты с совпадающим сроком объединяются в одну запись.
    """


class ProductRepository:
    """Запросы к позициям запасов пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self, telegram_id: int, status_code: str | None) -> list[Product]:
        """Продукты пользователя, при указанном статусе — только с ним."""
        statement = select(Product).where(Product.telegram_id == telegram_id)
        if status_code is not None:
            statement = statement.where(Product.status_code == status_code)
        statement = statement.order_by(Product.expiry_date, Product.id)
        return list((await self._session.scalars(statement)).all())

    async def get_by_id(self, telegram_id: int, product_id: int) -> Product | None:
        """Продукт пользователя по идентификатору.

        Владелец — часть условия: чужая позиция не находится, и обработчик
        отвечает 404, не раскрывая факта существования записи.
        """
        statement = select(Product).where(
            Product.id == product_id, Product.telegram_id == telegram_id
        )
        return await self._session.scalar(statement)

    async def create(self, telegram_id: int, fields: dict[str, Any]) -> Product:
        """Заводит позицию запасов."""
        product = Product(telegram_id=telegram_id, **fields)
        self._session.add(product)
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            raise DuplicateProductError from error
        return product

    async def update(self, product: Product, fields: dict[str, Any]) -> Product:
        """Меняет переданные поля позиции."""
        for name, value in fields.items():
            setattr(product, name, value)
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            raise DuplicateProductError from error
        return product

    async def set_status(self, product: Product, status_code: str) -> Product:
        """Отмечает продукт использованным или списанным.

        Физического удаления нет: статус меняется, запись остаётся
        в истории операций.
        """
        product.status_code = status_code
        await self._session.flush()
        return product

    async def get_active(self, telegram_id: int) -> list[Product]:
        """Продукты пользователя, которые есть в наличии.

        Использованные, списанные и удалённые из перечня не возвращаются:
        они остаются в таблице ради истории операций, но в подборе рецептов
        не участвуют.
        Порядок задан явно — от него зависит воспроизводимость подбора.
        """
        statement = (
            select(Product)
            .where(
                Product.telegram_id == telegram_id,
                Product.status_code == ProductStatusCode.IN_STOCK,
            )
            .order_by(Product.expiry_date, Product.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_expiring(
        self, telegram_id: int, threshold_days: int, today: date
    ) -> list[Product]:
        """Продукты, у которых остаточный срок не больше порога: τ ≤ threshold.

        Просроченные не возвращаются: их снимает с учёта задача списания,
        и повторно тревожить ими пользователя незачем. Благодаря этому
        порядок выполнения двух ежедневных задач не влияет на результат.
        """
        statement = (
            select(Product)
            .where(
                Product.telegram_id == telegram_id,
                Product.status_code == ProductStatusCode.IN_STOCK,
                Product.expiry_date >= today,
                Product.expiry_date <= today + timedelta(days=threshold_days),
            )
            .order_by(Product.expiry_date, Product.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def write_off_expired(self, today: date) -> int:
        """Переводит просроченные продукты в статус «списан».

        Продукты не удаляются физически — меняется только статус, история
        операций сохраняется. Списывается то, чей срок уже прошёл:
        в день истечения продукт ещё считается пригодным.

        Условие по статусу здесь не только для экономии: позиция, удалённая
        пользователем из перечня, не должна задним числом превратиться
        в списанную и завысить статистику пищевых потерь.

        :return: число списанных позиций
        """
        statement = (
            update(Product)
            .where(
                Product.status_code == ProductStatusCode.IN_STOCK,
                Product.expiry_date < today,
            )
            .values(status_code=ProductStatusCode.WRITTEN_OFF)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(statement)
        return result.rowcount
