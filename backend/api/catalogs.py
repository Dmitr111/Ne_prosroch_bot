"""Эндпоинты справочников.

Категории и ингредиенты наполняются при развёртывании и только читаются:
пользовательского редактирования справочников и роли администратора
в приложении нет. Места хранения принадлежат пользователю.
"""

from fastapi import APIRouter

from backend.api.deps import Catalogs, CurrentUser
from backend.api.schemas import CategoryRead, IngredientRead, StoragePlaceRead

router = APIRouter(tags=["catalogs"])


@router.get("/storage-places", response_model=list[StoragePlaceRead])
async def list_storage_places(
    user: CurrentUser, catalogs: Catalogs
) -> list[StoragePlaceRead]:
    """Места хранения пользователя."""
    places = await catalogs.get_storage_places(user.telegram_id)
    return [StoragePlaceRead(id=place.id, name=place.name) for place in places]


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(user: CurrentUser, catalogs: Catalogs) -> list[CategoryRead]:
    """Справочник категорий."""
    categories = await catalogs.get_categories()
    return [CategoryRead(name=category.name) for category in categories]


@router.get("/ingredients", response_model=list[IngredientRead])
async def list_ingredients(
    user: CurrentUser, catalogs: Catalogs
) -> list[IngredientRead]:
    """Справочник ингредиентов для формы добавления продукта.

    Категория продукта отдельно не вводится, а выводится из выбранного
    ингредиента, поэтому она возвращается вместе с наименованием.
    """
    ingredients = await catalogs.get_ingredients()
    return [
        IngredientRead(name=item.name, category_name=item.category_name)
        for item in ingredients
    ]
