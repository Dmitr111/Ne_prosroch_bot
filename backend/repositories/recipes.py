"""Репозиторий рецептов.

Загружает рецепты вместе с ингредиентами и подбирает кандидатов по
списку продуктов пользователя.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import Recipe


class RecipeRepository:
    """Запросы к справочнику рецептов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> list[Recipe]:
        """Все рецепты вместе с составом.

        Состав подтягивается ``selectinload`` — одним дополнительным
        запросом на всю выборку, а не по запросу на рецепт: обращение
        к ``recipe.ingredients`` в асинхронной сессии иначе привело бы
        и к N+1, и к ошибке ленивой загрузки вне greenlet-контекста.

        Сортировка по ``title`` обязательна. Жадный алгоритм при равном
        приросте берёт первый рецепт по порядку, поэтому без явного
        ORDER BY результат подбора зависел бы от того, в каком порядке
        СУБД вернула строки, и эксперимент третьей главы перестал бы
        воспроизводиться.
        """
        statement = (
            select(Recipe).options(selectinload(Recipe.ingredients)).order_by(Recipe.title)
        )
        return list((await self._session.scalars(statement)).all())
