"""Эндпоинт подбора рецептов.

Второй вход в процесс из модели главы 2: пользователь запрашивает подбор
сам, не дожидаясь уведомления. Отсюда источник запуска by_request —
в отличие от by_expiry, который ставит планировщик.
"""

from fastapi import APIRouter

from backend.api.deps import CurrentUser, Recommendations
from backend.api.schemas import RecipeRead
from backend.core.service import RecommendationTrigger

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=list[RecipeRead])
async def get_recommendations(
    user: CurrentUser, service: Recommendations
) -> list[RecipeRead]:
    """Рецепты под истекающие продукты пользователя.

    Вместе с рецептом возвращается его покрытие: какие позиции запасов он
    спасает и какие ингредиенты в составе выделять. Эти данные — результат
    работы жадного алгоритма, повторно вычислять их на клиенте нельзя:
    там нет ни весов срочности, ни порядка отбора, а без порядка один
    продукт засчитался бы сразу нескольким рецептам.

    Пустой список — допустимый ответ: подходящих полностью обеспеченных
    рецептов может не найтись.
    """
    recommendations = await service.get_recommendations(
        user.telegram_id, RecommendationTrigger.BY_REQUEST
    )
    return [
        RecipeRead(
            title=item.recipe.title,
            description=item.recipe.description,
            cooking_time_min=item.recipe.cooking_time_min,
            ingredients=[link.ingredient_name for link in item.recipe.ingredients],
            covered_product_ids=list(item.covered_product_ids),
            covered_ingredients=list(item.covered_ingredients),
            covered_weight=item.covered_weight,
        )
        for item in recommendations
    ]
