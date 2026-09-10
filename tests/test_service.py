"""Тесты сценария подбора рекомендаций.

Репозитории подставные: сервис проверяется без подключения к БД и без
импорта моделей SQLAlchemy — ему достаточно, чтобы у объектов были нужные
атрибуты. Так тест не зависит ни от .env, ни от поднятой PostgreSQL.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from backend.core.service import RecommendationService, RecommendationTrigger

TODAY = date(2026, 3, 10)


# ---------------------------------------------------------------------------
# Подставные данные и репозитории
# ---------------------------------------------------------------------------


@dataclass
class FakeSettings:
    telegram_id: int = 1
    horizon_days: int = 7
    recommend_limit: int = 5


@dataclass
class FakeProduct:
    id: int
    ingredient_name: str
    expiry_date: date


@dataclass
class FakeLink:
    ingredient_name: str


@dataclass
class FakeRecipe:
    title: str
    ingredients: list[FakeLink]


@dataclass
class SavedSession:
    telegram_id: int
    trigger: str
    horizon_days: int
    k: int
    items: list[tuple[str, int]]


class FakeSettingsRepository:
    def __init__(self, settings: FakeSettings) -> None:
        self._settings = settings
        self.calls: list[int] = []

    async def get(self, telegram_id: int) -> FakeSettings:
        self.calls.append(telegram_id)
        return self._settings


class FakeProductRepository:
    def __init__(self, products: list[FakeProduct]) -> None:
        self._products = products
        self.calls: list[int] = []

    async def get_active(self, telegram_id: int) -> list[FakeProduct]:
        self.calls.append(telegram_id)
        return list(self._products)


class FakeRecipeRepository:
    def __init__(self, recipes: list[FakeRecipe]) -> None:
        self._recipes = recipes
        self.calls = 0

    async def get_all(self) -> list[FakeRecipe]:
        self.calls += 1
        return list(self._recipes)


class FakeRecommendationRepository:
    def __init__(self) -> None:
        self.saved: list[SavedSession] = []

    async def save(
        self,
        telegram_id: int,
        trigger: str,
        horizon_days: int,
        k: int,
        items,
    ) -> SavedSession:
        session = SavedSession(
            telegram_id=telegram_id,
            trigger=trigger,
            horizon_days=horizon_days,
            k=k,
            items=list(items),
        )
        self.saved.append(session)
        return session


def product(product_id: int, ingredient_name: str, days_left: int) -> FakeProduct:
    return FakeProduct(
        id=product_id,
        ingredient_name=ingredient_name,
        expiry_date=TODAY + timedelta(days=days_left),
    )


def recipe(title: str, *ingredient_names: str) -> FakeRecipe:
    return FakeRecipe(
        title=title, ingredients=[FakeLink(name) for name in ingredient_names]
    )


@dataclass
class Fixture:
    service: RecommendationService
    saved: FakeRecommendationRepository
    settings: FakeSettingsRepository
    products: FakeProductRepository
    recipes: FakeRecipeRepository


def build(
    products: list[FakeProduct],
    recipes: list[FakeRecipe],
    settings: FakeSettings | None = None,
) -> Fixture:
    settings_repo = FakeSettingsRepository(settings or FakeSettings())
    products_repo = FakeProductRepository(products)
    recipes_repo = FakeRecipeRepository(recipes)
    saved_repo = FakeRecommendationRepository()
    service = RecommendationService(
        products=products_repo,
        recipes=recipes_repo,
        settings=settings_repo,
        recommendations=saved_repo,
    )
    return Fixture(service, saved_repo, settings_repo, products_repo, recipes_repo)


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_recipes_in_selection_order() -> None:
    """Возвращаются модели рецептов в порядке отбора."""
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),  # вес 6
            product(2, "картофель", days_left=5),  # вес 2
        ],
        recipes=[recipe("Коктейль", "молоко"), recipe("Пюре", "картофель")],
    )

    result = await fixture.service.get_recommendations(1, today=TODAY)

    assert [item.recipe.title for item in result] == ["Коктейль", "Пюре"]
    # Возвращаются именно объекты из репозитория, а не структуры алгоритма
    assert result[0].recipe.ingredients[0].ingredient_name == "молоко"


@pytest.mark.asyncio
async def test_coverage_is_returned_with_each_recipe() -> None:
    """Покрытие приходит вместе с рецептом: продукты, ингредиенты, вес."""
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),  # вес 6
            product(2, "куриное яйцо", days_left=4),  # вес 3
        ],
        recipes=[recipe("Омлет", "молоко", "куриное яйцо")],
    )

    [omelette] = await fixture.service.get_recommendations(1, today=TODAY)

    assert omelette.covered_product_ids == (1, 2)
    assert omelette.covered_ingredients == ("куриное яйцо", "молоко")
    assert omelette.covered_weight == 9


@pytest.mark.asyncio
async def test_coverage_does_not_overlap_between_recipes() -> None:
    """Продукт засчитывается тому рецепту, который взял его первым.

    Молоко входит в оба рецепта, но спасает его омлет; блинам остаётся
    только мука. Именно поэтому пересечение нельзя считать на клиенте:
    без порядка отбора молоко попало бы в оба набора и списалось дважды.
    """
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),  # вес 6
            product(2, "куриное яйцо", days_left=4),  # вес 3
            product(3, "мука", days_left=6),  # вес 1
        ],
        recipes=[
            recipe("Омлет", "молоко", "куриное яйцо"),
            recipe("Блины", "молоко", "мука"),
        ],
    )

    omelette, pancakes = await fixture.service.get_recommendations(1, today=TODAY)

    assert omelette.covered_product_ids == (1, 2)
    assert pancakes.covered_product_ids == (3,)
    assert pancakes.covered_ingredients == ("мука",)
    # Прирост второго рецепта — только мука, а не молоко с мукой
    assert pancakes.covered_weight == 1


@pytest.mark.asyncio
async def test_coverage_skips_products_with_spare_time() -> None:
    """Продукт с запасом по сроку рецепт покрывает, но в набор не входит.

    Он не истекает, подсвечивать и списывать его незачем, и в прирост
    полезности он вносит ноль.
    """
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),  # вес 6
            product(2, "мука", days_left=200),  # вес 0
        ],
        recipes=[recipe("Блины", "молоко", "мука")],
    )

    [pancakes] = await fixture.service.get_recommendations(1, today=TODAY)

    assert pancakes.covered_product_ids == (1,)
    assert pancakes.covered_ingredients == ("молоко",)
    assert pancakes.covered_weight == 6


@pytest.mark.asyncio
async def test_coverage_weight_matches_saved_history() -> None:
    """covered_weight в ответе и в журнале подбора — одно и то же число."""
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),
            product(2, "куриное яйцо", days_left=4),
            product(3, "мука", days_left=6),
        ],
        recipes=[
            recipe("Омлет", "молоко", "куриное яйцо"),
            recipe("Блины", "молоко", "мука"),
        ],
    )

    result = await fixture.service.get_recommendations(1, today=TODAY)

    assert fixture.saved.saved[0].items == [
        (item.recipe.title, item.covered_weight) for item in result
    ]


@pytest.mark.asyncio
async def test_uses_settings_for_horizon_and_limit() -> None:
    """Горизонт T и ограничение k берутся из настроек пользователя."""
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),
            product(2, "картофель", days_left=2),
            product(3, "мука", days_left=3),
        ],
        recipes=[
            recipe("Коктейль", "молоко"),
            recipe("Пюре", "картофель"),
            recipe("Лепёшки", "мука"),
        ],
        settings=FakeSettings(horizon_days=7, recommend_limit=2),
    )

    result = await fixture.service.get_recommendations(1, today=TODAY)

    assert len(result) == 2
    assert fixture.saved.saved[0].k == 2
    assert fixture.saved.saved[0].horizon_days == 7


@pytest.mark.asyncio
async def test_horizon_cuts_off_distant_products() -> None:
    """Продукт за горизонтом имеет нулевой вес и рецепт под него не берётся."""
    fixture = build(
        products=[product(1, "молоко", days_left=30)],
        recipes=[recipe("Коктейль", "молоко")],
        settings=FakeSettings(horizon_days=7),
    )

    assert await fixture.service.get_recommendations(1, today=TODAY) == []


@pytest.mark.asyncio
async def test_covered_weight_is_marginal_not_total() -> None:
    """covered_weight — прирост на своём шаге, а не сумма весов состава.

    Молоко входит в оба рецепта. Первый забирает молоко и яйцо, второму
    достаётся только мука, поэтому в истории у него 1, а не 6 + 1.
    """
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),  # вес 6
            product(2, "куриное яйцо", days_left=4),  # вес 3
            product(3, "мука", days_left=6),  # вес 1
        ],
        recipes=[
            recipe("Омлет", "молоко", "куриное яйцо"),
            recipe("Блины", "молоко", "мука"),
        ],
    )

    await fixture.service.get_recommendations(1, today=TODAY)

    assert fixture.saved.saved[0].items == [("Омлет", 9), ("Блины", 1)]
    # Сумма приростов равна полезности набора V(S)
    assert sum(weight for _, weight in fixture.saved.saved[0].items) == 10


@pytest.mark.asyncio
async def test_saves_session_with_trigger() -> None:
    """Источник запуска сохраняется как есть."""
    fixture = build(
        products=[product(1, "молоко", days_left=0)],
        recipes=[recipe("Коктейль", "молоко")],
    )

    await fixture.service.get_recommendations(
        42, RecommendationTrigger.BY_EXPIRY, today=TODAY
    )

    saved = fixture.saved.saved[0]
    assert saved.telegram_id == 42
    assert saved.trigger == RecommendationTrigger.BY_EXPIRY
    assert saved.items == [("Коктейль", 7)]


@pytest.mark.asyncio
async def test_default_trigger_is_by_request() -> None:
    """Без указания источника считается, что подбор запросил пользователь."""
    fixture = build(
        products=[product(1, "молоко", days_left=0)],
        recipes=[recipe("Коктейль", "молоко")],
    )

    await fixture.service.get_recommendations(1, today=TODAY)

    assert fixture.saved.saved[0].trigger == RecommendationTrigger.BY_REQUEST


@pytest.mark.asyncio
async def test_empty_selection_is_still_recorded() -> None:
    """Сеанс сохраняется и тогда, когда подбор ничего не дал.

    Информирование происходит в любом случае, а для эксперимента важно,
    что запуск был и результат оказался пустым.
    """
    fixture = build(
        products=[product(1, "чай", days_left=0)],
        recipes=[recipe("Коктейль", "молоко")],
    )

    result = await fixture.service.get_recommendations(1, today=TODAY)

    assert result == []
    assert len(fixture.saved.saved) == 1
    assert fixture.saved.saved[0].items == []


@pytest.mark.asyncio
async def test_no_products_at_all() -> None:
    """Пустые запасы — пустой результат, без обращения к алгоритму."""
    fixture = build(products=[], recipes=[recipe("Коктейль", "молоко")])

    assert await fixture.service.get_recommendations(1, today=TODAY) == []


@pytest.mark.asyncio
async def test_incomplete_recipe_is_skipped() -> None:
    """При α = 1 рецепт с недостающим ингредиентом не предлагается."""
    fixture = build(
        products=[product(1, "молоко", days_left=1)],
        recipes=[
            recipe("Омлет", "молоко", "куриное яйцо"),
            recipe("Коктейль", "молоко"),
        ],
    )

    result = await fixture.service.get_recommendations(1, today=TODAY)

    assert [item.recipe.title for item in result] == ["Коктейль"]


@pytest.mark.asyncio
async def test_expired_product_is_prioritised() -> None:
    """Просроченный продукт весит больше истекающего сегодня."""
    fixture = build(
        products=[
            product(1, "молоко", days_left=0),  # вес 7
            product(2, "картофель", days_left=-3),  # вес 10
        ],
        recipes=[recipe("Коктейль", "молоко"), recipe("Пюре", "картофель")],
    )

    result = await fixture.service.get_recommendations(1, today=TODAY)

    assert [item.recipe.title for item in result] == ["Пюре", "Коктейль"]


@pytest.mark.asyncio
async def test_two_products_with_same_ingredient_both_counted() -> None:
    """Две пачки молока с разными сроками дают суммарный вес одному рецепту."""
    fixture = build(
        products=[
            product(1, "молоко", days_left=1),  # вес 6
            product(2, "молоко", days_left=5),  # вес 2
        ],
        recipes=[recipe("Коктейль", "молоко")],
    )

    await fixture.service.get_recommendations(1, today=TODAY)

    assert fixture.saved.saved[0].items == [("Коктейль", 8)]


@pytest.mark.asyncio
async def test_repositories_are_queried_for_the_same_user() -> None:
    """Данные читаются по одному пользователю и по одному разу."""
    fixture = build(
        products=[product(1, "молоко", days_left=1)],
        recipes=[recipe("Коктейль", "молоко")],
    )

    await fixture.service.get_recommendations(77, today=TODAY)

    assert fixture.settings.calls == [77]
    assert fixture.products.calls == [77]
    assert fixture.recipes.calls == 1
