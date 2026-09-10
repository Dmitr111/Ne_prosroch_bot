"""Репозиторий справочников.

Категории и ингредиенты наполняются при развёртывании и пользователем
не правятся. Места хранения — данные пользователя, но для формы добавления
продукта они выступают таким же списком выбора, поэтому лежат здесь же.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Category, Ingredient, StoragePlace

# Места хранения, которые заводятся пользователю при первом обращении.
# Эндпоинта для создания мест в API нет, поэтому без них список выбора
# в форме был пуст, а перечень никогда не группировался по местам,
# как на рисунке 2.4
DEFAULT_STORAGE_PLACES = ("Холодильник", "Морозилка", "Кладовая")


class CatalogRepository:
    """Запросы к справочникам и местам хранения."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_categories(self) -> list[Category]:
        statement = select(Category).order_by(Category.name)
        return list((await self._session.scalars(statement)).all())

    async def get_ingredients(self) -> list[Ingredient]:
        statement = select(Ingredient).order_by(Ingredient.name)
        return list((await self._session.scalars(statement)).all())

    async def ingredient_exists(self, name: str) -> bool:
        """Есть ли такой ингредиент в справочнике.

        Продукт без ингредиента не поддерживается: при α = 1 он не смог бы
        участвовать в подборе, поэтому наименование проверяется до вставки.
        """
        statement = select(Ingredient.name).where(Ingredient.name == name)
        return await self._session.scalar(statement) is not None

    async def get_storage_places(self, telegram_id: int) -> list[StoragePlace]:
        """Места хранения пользователя; при первом обращении — стандартные.

        Устроено как настройки по умолчанию: отдельного шага настройки нет,
        записи появляются при первом чтении. ON CONFLICT DO NOTHING на
        UNIQUE(telegram_id, name) защищает от гонки двух одновременных
        первых запросов — второй просто ничего не вставит.
        """
        statement = (
            select(StoragePlace)
            .where(StoragePlace.telegram_id == telegram_id)
            .order_by(StoragePlace.name)
        )
        places = list((await self._session.scalars(statement)).all())
        if places:
            return places

        rows = [{"telegram_id": telegram_id, "name": name} for name in DEFAULT_STORAGE_PLACES]
        await self._session.execute(
            insert(StoragePlace)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["telegram_id", "name"])
        )
        return list((await self._session.scalars(statement)).all())

    async def get_storage_place(
        self, telegram_id: int, place_id: int
    ) -> StoragePlace | None:
        """Место хранения пользователя. Чужое не находится."""
        statement = select(StoragePlace).where(
            StoragePlace.id == place_id, StoragePlace.telegram_id == telegram_id
        )
        return await self._session.scalar(statement)
