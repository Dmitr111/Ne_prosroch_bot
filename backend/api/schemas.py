"""Схемы запросов и ответов REST API.

Отделены от моделей SQLAlchemy: модель описывает хранение, схема —
контракт с mini app. Благодаря этому изменение физической схемы не течёт
наружу, а форма ответа не диктует форму таблицы.
"""

from datetime import date, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Статусы, которые пользователь проставляет отметкой. Четвёртый статус
# справочника, removed, сюда не входит: удаление из перечня идёт через
# DELETE, а не отметкой, и по смыслу это не пищевые потери
StatusCode = Literal["in_stock", "used", "written_off"]


class ProductRead(BaseModel):
    """Позиция запасов в ответе API."""

    id: int
    name: str
    expiry_date: date
    manufacture_date: date | None
    ingredient_name: str
    storage_place_id: int | None
    status_code: str
    quantity: float
    unit: str
    # Остаточный срок в днях, отрицательный — просрочено
    days_left: int
    # Цвет индикатора: green, yellow, red
    urgency: str


class ProductCreate(BaseModel):
    """Добавление позиции запасов."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    expiry_date: date
    manufacture_date: date | None = None
    # Обязателен: продукт без ингредиента не участвовал бы в подборе
    ingredient_name: str = Field(min_length=1, max_length=128)
    storage_place_id: int | None = None
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=10, decimal_places=3)
    unit: str = Field(default="шт", min_length=1, max_length=16)

    @model_validator(mode="after")
    def check_dates(self) -> "ProductCreate":
        """Дублирует CHECK-ограничение схемы, но отвечает понятной ошибкой."""
        if self.manufacture_date and self.expiry_date < self.manufacture_date:
            raise ValueError("срок годности раньше даты изготовления")
        return self


class ProductUpdate(BaseModel):
    """Редактирование позиции: меняются только переданные поля.

    ``None`` здесь означает «поле не передано». Явно обнулить можно только
    дату изготовления и место хранения — остальные колонки обязательны,
    и попытка стереть их отклоняется, а не доходит до СУБД.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    expiry_date: date | None = None
    manufacture_date: date | None = None
    ingredient_name: str | None = Field(default=None, min_length=1, max_length=128)
    storage_place_id: int | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    unit: str | None = Field(default=None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def check_required_not_cleared(self) -> "ProductUpdate":
        for name in ("name", "expiry_date", "ingredient_name", "quantity", "unit"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"поле {name} нельзя очистить")
        return self


class ProductStatusUpdate(BaseModel):
    """Отметка об использовании или списании."""

    status_code: StatusCode


class StoragePlaceRead(BaseModel):
    id: int
    name: str


class CategoryRead(BaseModel):
    name: str


class IngredientRead(BaseModel):
    name: str
    category_name: str


class RecipeRead(BaseModel):
    """Рецепт с составом и тем, что он спасает.

    Покрытие считает жадный алгоритм: продукт засчитывается рецепту,
    который взял его первым, поэтому наборы разных рецептов не
    пересекаются и клиенту не приходится вычислять это заново.
    """

    title: str
    description: str | None
    cooking_time_min: int | None
    ingredients: list[str]
    # Истекающие продукты пользователя, покрытые этим рецептом
    covered_product_ids: list[int]
    # Их ингредиенты — какие позиции состава выделять в интерфейсе
    covered_ingredients: list[str]
    # Прирост полезности, сумма весов покрытых продуктов
    covered_weight: int


class SettingsRead(BaseModel):
    """Параметры напоминаний и подбора."""

    notify_time: time
    threshold_days: int
    horizon_days: int
    recommend_limit: int


class SettingsUpdate(BaseModel):
    """Изменение параметров: меняются только переданные поля.

    Обнулить нельзя ни один: все четыре колонки обязательны.
    """

    notify_time: time | None = None
    threshold_days: int | None = Field(default=None, ge=1, le=30)
    # Горизонт планирования T из формулы веса срочности
    horizon_days: int | None = Field(default=None, ge=1, le=60)
    # Ограничение k на размер набора рецептов
    recommend_limit: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def check_required_not_cleared(self) -> "SettingsUpdate":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"поле {name} нельзя очистить")
        return self
