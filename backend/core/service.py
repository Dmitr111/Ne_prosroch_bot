"""RecommendationService — сценарий получения рекомендаций.

Связывает репозитории, UrgencyCalculator и GreedyRecommender: собирает
продукты и рецепты пользователя, считает срочность, запускает подбор и
возвращает готовый результат для API и уведомлений.

Единственная точка входа в подбор из REST API и из планировщика. Сам
в БД не ходит: все запросы — через репозитории, переданные в конструктор.
Модели SQLAlchemy импортируются только для аннотаций, поэтому модуль
остаётся проверяемым на подставных репозиториях без подключения к БД.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from backend.core.greedy import (
    GreedyRecommender,
    Product,
    Recipe,
    applicable_recipes,
    marginal_coverage,
)
from backend.core.urgency import UrgencyCalculator

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from backend.db.models import Product as ProductModel
    from backend.db.models import Recipe as RecipeModel
    from backend.repositories.products import ProductRepository
    from backend.repositories.recipes import RecipeRepository
    from backend.repositories.recommendations import RecommendationRepository
    from backend.repositories.settings import SettingsRepository


class RecommendationTrigger:
    """Источник запуска подбора, записывается в recommendation_sessions."""

    # Подбор запущен планировщиком при приближении срока годности
    BY_EXPIRY = "by_expiry"
    # Пользователь запросил подбор сам, не дожидаясь уведомления
    BY_REQUEST = "by_request"


@dataclass(frozen=True)
class Recommendation:
    """Отобранный рецепт вместе с тем, что он спасает.

    Состав покрытия считает жадный алгоритм, и только он знает и веса,
    и порядок отбора: продукт засчитывается тому рецепту, который взял
    его первым, поэтому списки разных рецептов не пересекаются.
    Клиенту это пересечение заново не вычислить.

    В ``covered_products`` попадают только продукты с ненулевым весом —
    те самые истекающие, ради которых рецепт и выбран. Продукт с запасом
    по сроку рецепт покрывает, но в прирост полезности не вносит ничего.
    """

    recipe: RecipeModel
    # Идентификаторы истекающих продуктов, покрытых этим рецептом
    covered_product_ids: tuple[int, ...]
    # Их типовые ингредиенты — для выделения в составе рецепта
    covered_ingredients: tuple[str, ...]
    # Прирост полезности на своём шаге, равен сумме весов покрытых продуктов
    covered_weight: int


class RecommendationService:
    """Фасад подбора рецептов."""

    def __init__(
        self,
        products: ProductRepository,
        recipes: RecipeRepository,
        settings: SettingsRepository,
        recommendations: RecommendationRepository,
    ) -> None:
        self._products = products
        self._recipes = recipes
        self._settings = settings
        self._recommendations = recommendations

    async def get_recommendations(
        self,
        telegram_id: int,
        trigger: str = RecommendationTrigger.BY_REQUEST,
        *,
        today: date | None = None,
    ) -> list[Recommendation]:
        """Подбирает рецепты под истекающие продукты пользователя.

        :param telegram_id: пользователь, для которого идёт подбор
        :param trigger: источник запуска, см. RecommendationTrigger
        :param today: дата отсчёта остаточных сроков; по умолчанию
            сегодняшняя. Задаётся явно в тестах и при пересчёте задним числом
        :return: рекомендации в порядке отбора, то есть в порядке убывания
            прироста полезности; каждая несёт рецепт и покрытые им продукты
        """
        if today is None:
            today = date.today()

        settings = await self._settings.get(telegram_id)
        horizon_days = settings.horizon_days
        limit = settings.recommend_limit

        products = await self._products.get_active(telegram_id)
        recipe_models = await self._recipes.get_all()

        weights = self._weights(products, horizon_days, today)
        candidates = applicable_recipes(
            [self._to_recipe(model) for model in recipe_models], weights
        )
        selected = GreedyRecommender.recommend(candidates, weights, limit)
        coverage = marginal_coverage(selected, weights)

        by_title = {model.title: model for model in recipe_models}
        recommendations = [
            self._to_recommendation(by_title[recipe.title], covered, weights)
            for recipe, covered in zip(selected, coverage, strict=True)
        ]

        await self._recommendations.save(
            telegram_id=telegram_id,
            trigger=trigger,
            horizon_days=horizon_days,
            k=limit,
            items=[
                (item.recipe.title, item.covered_weight) for item in recommendations
            ],
        )

        return recommendations

    @staticmethod
    def _to_recommendation(
        model: RecipeModel,
        covered: Sequence[Product],
        weights: Mapping[Product, int],
    ) -> Recommendation:
        """Собирает рекомендацию по результату шага жадного алгоритма.

        Продукты с нулевым весом отбрасываются: рецепт их покрывает,
        но выбран не из-за них, и в интерфейсе они выглядели бы
        истекающими, не будучи таковыми. На covered_weight это не влияет —
        нулевые слагаемые ничего не добавляют.
        """
        expiring = sorted(
            (product for product in covered if weights[product] > 0),
            key=lambda product: product.id,
        )
        return Recommendation(
            recipe=model,
            covered_product_ids=tuple(product.id for product in expiring),
            covered_ingredients=tuple(
                sorted({product.ingredient_name for product in expiring})
            ),
            covered_weight=sum(weights[product] for product in expiring),
        )

    @staticmethod
    def _weights(
        products: Sequence[ProductModel], horizon_days: int, today: date
    ) -> dict[Product, int]:
        """Веса срочности по позициям запасов.

        Каждая позиция считается отдельно, даже если ингредиент совпадает:
        две пачки молока с разными сроками дают разные веса.
        """
        weights: dict[Product, int] = {}
        for product in products:
            days_left = (product.expiry_date - today).days
            weights[Product(id=product.id, ingredient_name=product.ingredient_name)] = (
                UrgencyCalculator.weight(days_left, horizon_days)
            )
        return weights

    @staticmethod
    def _to_recipe(model: RecipeModel) -> Recipe:
        """Переводит рецепт из модели БД в структуру алгоритма."""
        return Recipe(
            title=model.title,
            ingredient_names=frozenset(
                link.ingredient_name for link in model.ingredients
            ),
        )
