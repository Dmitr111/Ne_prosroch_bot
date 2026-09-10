"""Тесты REST API.

Репозитории и авторизация подменяются через ``dependency_overrides``:
запросы идут по настоящим маршрутам, со схемами и валидацией, но без БД
и без Telegram. Отдельно проверяется сам разбор initData — чистой
функцией, на подписи, собранной тем же алгоритмом.
"""

import hashlib
import hmac
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.api import deps
from backend.api.deps import InitDataError, parse_init_data
from backend.core.service import RecommendationTrigger
from backend.main import app

TODAY = date.today()
BOT_TOKEN = "123456:TEST-TOKEN"
OWNER_ID = 1
STRANGER_PRODUCT_ID = 999


# ---------------------------------------------------------------------------
# Подставные данные и репозитории
# ---------------------------------------------------------------------------


@dataclass
class FakeUser:
    telegram_id: int = OWNER_ID
    username: str | None = "tester"


@dataclass
class FakeSettings:
    telegram_id: int = OWNER_ID
    notify_time: time = time(9, 0)
    threshold_days: int = 3
    horizon_days: int = 7
    recommend_limit: int = 5


@dataclass
class FakeProduct:
    id: int
    name: str
    expiry_date: date
    ingredient_name: str
    telegram_id: int = OWNER_ID
    manufacture_date: date | None = None
    storage_place_id: int | None = None
    status_code: str = "in_stock"
    quantity: Decimal = Decimal(1)
    unit: str = "шт"


@dataclass
class FakePlace:
    id: int
    name: str


@dataclass
class FakeCategory:
    name: str


@dataclass
class FakeIngredient:
    name: str
    category_name: str


@dataclass
class FakeLink:
    ingredient_name: str


@dataclass
class FakeRecipe:
    title: str
    description: str | None
    cooking_time_min: int | None
    ingredients: list[FakeLink]


@dataclass
class FakeRecommendation:
    """Результат подбора: рецепт вместе с покрытием, как его отдаёт сервис."""

    recipe: FakeRecipe
    covered_product_ids: tuple[int, ...]
    covered_ingredients: tuple[str, ...]
    covered_weight: int


class FakeProductRepository:
    """Хранит позиции в памяти, повторяя поведение настоящего репозитория."""

    def __init__(self, products: list[FakeProduct]) -> None:
        self.products = products
        self.next_id = max((item.id for item in products), default=0) + 1
        self.duplicate = False

    async def get_all(
        self, telegram_id: int, status_code: str | None
    ) -> list[FakeProduct]:
        return [
            item
            for item in self.products
            if item.telegram_id == telegram_id
            and (status_code is None or item.status_code == status_code)
        ]

    async def get_by_id(self, telegram_id: int, product_id: int) -> FakeProduct | None:
        for item in self.products:
            if item.id == product_id and item.telegram_id == telegram_id:
                return item
        return None

    async def create(self, telegram_id: int, fields: dict[str, Any]) -> FakeProduct:
        from backend.repositories.products import DuplicateProductError

        if self.duplicate:
            raise DuplicateProductError
        product = FakeProduct(id=self.next_id, telegram_id=telegram_id, **fields)
        self.next_id += 1
        self.products.append(product)
        return product

    async def update(
        self, product: FakeProduct, fields: dict[str, Any]
    ) -> FakeProduct:
        for name, value in fields.items():
            setattr(product, name, value)
        return product

    async def set_status(self, product: FakeProduct, status_code: str) -> FakeProduct:
        product.status_code = status_code
        return product


class FakeCatalogRepository:
    def __init__(self) -> None:
        self.categories = [FakeCategory("молочные продукты"), FakeCategory("бакалея")]
        self.ingredients = [
            FakeIngredient("молоко", "молочные продукты"),
            FakeIngredient("мука", "бакалея"),
        ]
        self.places = [FakePlace(1, "Холодильник"), FakePlace(2, "Морозилка")]

    async def get_categories(self) -> list[FakeCategory]:
        return self.categories

    async def get_ingredients(self) -> list[FakeIngredient]:
        return self.ingredients

    async def ingredient_exists(self, name: str) -> bool:
        return any(item.name == name for item in self.ingredients)

    async def get_storage_places(self, telegram_id: int) -> list[FakePlace]:
        return self.places

    async def get_storage_place(
        self, telegram_id: int, place_id: int
    ) -> FakePlace | None:
        return next((item for item in self.places if item.id == place_id), None)


class FakeSettingsRepository:
    def __init__(self, settings: FakeSettings) -> None:
        self.settings = settings

    async def get(self, telegram_id: int) -> FakeSettings:
        return self.settings

    async def update(self, settings: FakeSettings, fields: dict) -> FakeSettings:
        for name, value in fields.items():
            setattr(settings, name, value)
        return settings


class FakeRecommendationService:
    def __init__(self, recipes: list[FakeRecommendation]) -> None:
        self.recipes = recipes
        self.calls: list[tuple[int, str]] = []

    async def get_recommendations(
        self, telegram_id: int, trigger: str = RecommendationTrigger.BY_REQUEST
    ) -> list[FakeRecommendation]:
        self.calls.append((telegram_id, trigger))
        return self.recipes


@dataclass
class Environment:
    """Всё, что подменено на время теста."""

    products: FakeProductRepository
    catalogs: FakeCatalogRepository
    settings: FakeSettingsRepository
    service: FakeRecommendationService
    user: FakeUser = field(default_factory=FakeUser)


@pytest.fixture
def env() -> Iterator[Environment]:
    """Подменяет зависимости приложения на подставные."""
    environment = Environment(
        products=FakeProductRepository(
            [
                FakeProduct(1, "Молоко", TODAY + timedelta(days=2), "молоко"),
                FakeProduct(2, "Мука", TODAY + timedelta(days=200), "мука"),
                FakeProduct(
                    3,
                    "Кефир",
                    TODAY - timedelta(days=1),
                    "молоко",
                    status_code="written_off",
                ),
                # Чужая позиция: в ответах появляться не должна
                FakeProduct(
                    STRANGER_PRODUCT_ID,
                    "Чужое молоко",
                    TODAY,
                    "молоко",
                    telegram_id=OWNER_ID + 1,
                ),
            ]
        ),
        catalogs=FakeCatalogRepository(),
        settings=FakeSettingsRepository(FakeSettings()),
        service=FakeRecommendationService(
            [
                FakeRecommendation(
                    recipe=FakeRecipe(
                        "Блины на молоке",
                        "Тонкое тесто, жарится на сковороде.",
                        40,
                        [FakeLink("молоко"), FakeLink("мука")],
                    ),
                    # Мука не истекает, поэтому в покрытие не попала
                    covered_product_ids=(1,),
                    covered_ingredients=("молоко",),
                    covered_weight=5,
                )
            ]
        ),
    )

    app.dependency_overrides[deps.get_current_user] = lambda: environment.user
    app.dependency_overrides[deps.get_product_repository] = lambda: environment.products
    app.dependency_overrides[deps.get_catalog_repository] = lambda: environment.catalogs
    app.dependency_overrides[deps.get_settings_repository] = lambda: environment.settings
    app.dependency_overrides[deps.get_recommendation_service] = lambda: environment.service

    yield environment

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


# ---------------------------------------------------------------------------
# Продукты
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_products_returns_only_in_stock_by_default(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.get("/products")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["Молоко", "Мука"]


@pytest.mark.asyncio
async def test_list_products_does_not_leak_other_users(
    client: AsyncClient, env: Environment
) -> None:
    """Чужие позиции не попадают в перечень."""
    response = await client.get("/products", params={"status": "all"})

    owners = {item["name"] for item in response.json()}
    assert "Чужое молоко" not in owners


@pytest.mark.asyncio
async def test_list_products_computes_days_left_and_colour(
    client: AsyncClient, env: Environment
) -> None:
    """Остаточный срок и цвет считаются от горизонта T из настроек."""
    response = await client.get("/products")

    milk, flour = response.json()
    assert milk["days_left"] == 2
    assert milk["urgency"] == "yellow"
    assert flour["urgency"] == "green"


@pytest.mark.asyncio
async def test_expired_product_is_red(client: AsyncClient, env: Environment) -> None:
    response = await client.get("/products", params={"status": "written_off"})

    kefir = response.json()[0]
    assert kefir["days_left"] == -1
    assert kefir["urgency"] == "red"


@pytest.mark.asyncio
async def test_create_product(client: AsyncClient, env: Environment) -> None:
    response = await client.post(
        "/products",
        json={
            "name": "Творог",
            "expiry_date": str(TODAY + timedelta(days=1)),
            "ingredient_name": "молоко",
            "quantity": 0.4,
            "unit": "кг",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Творог"
    assert body["quantity"] == 0.4
    assert body["status_code"] == "in_stock"
    assert body["urgency"] == "red" or body["days_left"] == 1


@pytest.mark.asyncio
async def test_create_product_requires_known_ingredient(
    client: AsyncClient, env: Environment
) -> None:
    """Ингредиент только из справочника: своего наименования быть не может."""
    response = await client.post(
        "/products",
        json={
            "name": "Печенье",
            "expiry_date": str(TODAY + timedelta(days=10)),
            "ingredient_name": "печенье",
        },
    )

    assert response.status_code == 422
    assert "справочник" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_product_without_ingredient_is_rejected(
    client: AsyncClient, env: Environment
) -> None:
    """Вариант «сохранить без ингредиента» не поддерживается."""
    response = await client.post(
        "/products",
        json={"name": "Печенье", "expiry_date": str(TODAY + timedelta(days=10))},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_rejects_non_positive_quantity(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.post(
        "/products",
        json={
            "name": "Молоко",
            "expiry_date": str(TODAY),
            "ingredient_name": "молоко",
            "quantity": 0,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_rejects_expiry_before_manufacture(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.post(
        "/products",
        json={
            "name": "Молоко",
            "expiry_date": str(TODAY),
            "manufacture_date": str(TODAY + timedelta(days=5)),
            "ingredient_name": "молоко",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_rejects_foreign_storage_place(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.post(
        "/products",
        json={
            "name": "Молоко",
            "expiry_date": str(TODAY),
            "ingredient_name": "молоко",
            "storage_place_id": 42,
        },
    )

    assert response.status_code == 422
    assert "Место хранения" in response.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_product_gives_conflict(
    client: AsyncClient, env: Environment
) -> None:
    """UNIQUE(telegram_id, name, expiry_date) наружу отдаётся как 409."""
    env.products.duplicate = True

    response = await client.post(
        "/products",
        json={
            "name": "Молоко",
            "expiry_date": str(TODAY + timedelta(days=2)),
            "ingredient_name": "молоко",
        },
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_product(client: AsyncClient, env: Environment) -> None:
    response = await client.patch("/products/1", json={"name": "Молоко 3,2 %"})

    assert response.status_code == 200
    assert response.json()["name"] == "Молоко 3,2 %"
    # Непереданные поля не тронуты
    assert response.json()["ingredient_name"] == "молоко"


@pytest.mark.asyncio
async def test_update_can_clear_optional_fields(
    client: AsyncClient, env: Environment
) -> None:
    """Дату изготовления и место хранения обнулить можно."""
    response = await client.patch(
        "/products/1", json={"manufacture_date": None, "storage_place_id": None}
    )

    assert response.status_code == 200
    assert response.json()["manufacture_date"] is None


@pytest.mark.asyncio
async def test_update_cannot_clear_required_fields(
    client: AsyncClient, env: Environment
) -> None:
    """Явный null в обязательном поле отклоняется, а не доходит до СУБД."""
    response = await client.patch("/products/1", json={"ingredient_name": None})

    assert response.status_code == 422
    product = await env.products.get_by_id(OWNER_ID, 1)
    assert product.ingredient_name == "молоко"


@pytest.mark.asyncio
async def test_update_foreign_product_gives_404(
    client: AsyncClient, env: Environment
) -> None:
    """Чужая запись — 404, а не 403: иначе ответ подтверждал бы её наличие."""
    response = await client.patch(
        f"/products/{STRANGER_PRODUCT_ID}", json={"name": "Моё теперь"}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_missing_product_gives_same_404(
    client: AsyncClient, env: Environment
) -> None:
    foreign = await client.patch(f"/products/{STRANGER_PRODUCT_ID}", json={"name": "A"})
    missing = await client.patch("/products/100500", json={"name": "A"})

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


@pytest.mark.asyncio
async def test_delete_product_marks_it_removed(
    client: AsyncClient, env: Environment
) -> None:
    """Удаление не физическое: проставляется «удалён», а не «списан».

    Разграничение существенное: written_off — реальные пищевые потери
    и материал для статистики третьей главы, removed — ошибочно внесённая
    позиция, потерями она не является.
    """
    response = await client.delete("/products/1")

    assert response.status_code == 204
    product = await env.products.get_by_id(OWNER_ID, 1)
    assert product is not None
    assert product.status_code == "removed"


@pytest.mark.asyncio
async def test_removed_product_leaves_the_stock_list(
    client: AsyncClient, env: Environment
) -> None:
    """Удалённая позиция пропадает из перечня в наличии, но не из базы."""
    await client.delete("/products/1")

    in_stock = await client.get("/products")
    removed = await client.get("/products", params={"status": "removed"})

    assert "Молоко" not in [item["name"] for item in in_stock.json()]
    assert [item["name"] for item in removed.json()] == ["Молоко"]


@pytest.mark.asyncio
async def test_removed_is_not_settable_by_status_endpoint(
    client: AsyncClient, env: Environment
) -> None:
    """Пометить «удалён» отметкой нельзя — только через DELETE."""
    response = await client.post("/products/1/status", json={"status_code": "removed"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_foreign_product_gives_404(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.delete(f"/products/{STRANGER_PRODUCT_ID}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_product_status(client: AsyncClient, env: Environment) -> None:
    response = await client.post("/products/1/status", json={"status_code": "used"})

    assert response.status_code == 200
    assert response.json()["status_code"] == "used"


@pytest.mark.asyncio
async def test_unknown_status_is_rejected(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.post("/products/1/status", json={"status_code": "съеден"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_storage_places(client: AsyncClient, env: Environment) -> None:
    response = await client.get("/storage-places")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Холодильник", "Морозилка"]


@pytest.mark.asyncio
async def test_list_categories(client: AsyncClient, env: Environment) -> None:
    response = await client.get("/categories")

    assert response.status_code == 200
    assert {"name": "бакалея"} in response.json()


@pytest.mark.asyncio
async def test_list_ingredients_carries_category(
    client: AsyncClient, env: Environment
) -> None:
    """Категория выводится из ингредиента, отдельно её не вводят."""
    response = await client.get("/ingredients")

    assert response.json()[0] == {"name": "молоко", "category_name": "молочные продукты"}


# ---------------------------------------------------------------------------
# Рекомендации
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommendations_use_by_request_trigger(
    client: AsyncClient, env: Environment
) -> None:
    """Подбор из приложения — это второй вход в процесс, by_request."""
    response = await client.get("/recommendations")

    assert response.status_code == 200
    assert env.service.calls == [(OWNER_ID, RecommendationTrigger.BY_REQUEST)]


@pytest.mark.asyncio
async def test_recommendations_return_recipe_with_composition(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.get("/recommendations")

    recipe = response.json()[0]
    assert recipe["title"] == "Блины на молоке"
    assert recipe["cooking_time_min"] == 40
    assert recipe["ingredients"] == ["молоко", "мука"]


@pytest.mark.asyncio
async def test_recommendations_carry_coverage(
    client: AsyncClient, env: Environment
) -> None:
    """Покрытие приходит с сервера: клиенту нечего пересчитывать.

    Мука в составе рецепта есть, но не истекает, поэтому в покрытие
    не входит — ни в подсветку, ни в списание.
    """
    response = await client.get("/recommendations")

    recipe = response.json()[0]
    assert recipe["covered_product_ids"] == [1]
    assert recipe["covered_ingredients"] == ["молоко"]
    assert recipe["covered_weight"] == 5


@pytest.mark.asyncio
async def test_empty_recommendations_are_valid_answer(
    client: AsyncClient, env: Environment
) -> None:
    env.service.recipes = []

    response = await client.get("/recommendations")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_settings(client: AsyncClient, env: Environment) -> None:
    response = await client.get("/settings")

    assert response.status_code == 200
    assert response.json() == {
        "notify_time": "09:00:00",
        "threshold_days": 3,
        "horizon_days": 7,
        "recommend_limit": 5,
    }


@pytest.mark.asyncio
async def test_update_settings_changes_only_given_fields(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.patch("/settings", json={"horizon_days": 14})

    assert response.status_code == 200
    assert response.json()["horizon_days"] == 14
    assert response.json()["recommend_limit"] == 5


@pytest.mark.asyncio
async def test_update_settings_validates_bounds(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.patch("/settings", json={"recommend_limit": 0})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_settings_cannot_be_cleared(
    client: AsyncClient, env: Environment
) -> None:
    response = await client.patch("/settings", json={"horizon_days": None})

    assert response.status_code == 422
    assert env.settings.settings.horizon_days == 7


@pytest.mark.asyncio
async def test_horizon_change_affects_colour(
    client: AsyncClient, env: Environment
) -> None:
    """Горизонт из настроек — тот же, что в весовой функции подбора."""
    env.settings.settings.horizon_days = 1

    response = await client.get("/products")

    milk = response.json()[0]
    assert milk["days_left"] == 2
    assert milk["urgency"] == "green"


# ---------------------------------------------------------------------------
# Авторизация
# ---------------------------------------------------------------------------


def signature_of(payload: dict[str, str], bot_token: str = BOT_TOKEN) -> str:
    """Подпись параметров тем же алгоритмом, что применяет Telegram."""
    check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()


def sign_init_data(payload: dict[str, str], bot_token: str = BOT_TOKEN) -> str:
    """Собирает initData с корректной подписью."""
    return urlencode({**payload, "hash": signature_of(payload, bot_token)})


def init_data_payload(
    telegram_id: int = 42, auth_date: datetime | None = None
) -> dict[str, str]:
    moment = auth_date or datetime.now(tz=timezone.utc)
    return {
        "auth_date": str(int(moment.timestamp())),
        "query_id": "AAA",
        "user": json.dumps(
            {"id": telegram_id, "username": "tester"}, ensure_ascii=False
        ),
    }


def test_valid_init_data_is_accepted() -> None:
    user = parse_init_data(sign_init_data(init_data_payload()), BOT_TOKEN)

    assert user.telegram_id == 42
    assert user.username == "tester"


def test_tampered_init_data_is_rejected() -> None:
    """Подмена пользователя при сохранённой подписи не проходит.

    Ровно та атака, от которой защищает проверка: подставить чужой
    telegram_id и получить доступ к чужим данным.
    """
    payload = init_data_payload(telegram_id=42)
    forged = {
        **payload,
        "user": json.dumps({"id": 43, "username": "tester"}, ensure_ascii=False),
        "hash": signature_of(payload),
    }

    with pytest.raises(InitDataError):
        parse_init_data(urlencode(forged), BOT_TOKEN)


def test_init_data_signed_by_other_token_is_rejected() -> None:
    init_data = sign_init_data(init_data_payload(), bot_token="999:OTHER-TOKEN")

    with pytest.raises(InitDataError):
        parse_init_data(init_data, BOT_TOKEN)


def test_init_data_without_hash_is_rejected() -> None:
    with pytest.raises(InitDataError):
        parse_init_data(urlencode(init_data_payload()), BOT_TOKEN)


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(InitDataError):
        parse_init_data("", BOT_TOKEN)


def test_expired_init_data_is_rejected() -> None:
    """Перехваченная строка не должна годиться вечно."""
    old = datetime.now(tz=timezone.utc) - timedelta(days=2)
    init_data = sign_init_data(init_data_payload(auth_date=old))

    with pytest.raises(InitDataError):
        parse_init_data(init_data, BOT_TOKEN)


def test_init_data_within_ttl_is_accepted() -> None:
    recent = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    init_data = sign_init_data(init_data_payload(auth_date=recent))

    assert parse_init_data(init_data, BOT_TOKEN).telegram_id == 42


def test_init_data_without_user_is_rejected() -> None:
    payload = init_data_payload()
    del payload["user"]

    with pytest.raises(InitDataError):
        parse_init_data(sign_init_data(payload), BOT_TOKEN)


@pytest.mark.asyncio
async def test_request_without_init_data_gives_401(client: AsyncClient) -> None:
    """Без подписи API не отвечает: зависимость авторизации не подменена."""
    response = await client.get("/products")

    assert response.status_code == 401
