"""Эндпоинты продуктов.

Перечень, добавление, редактирование, удаление и отметка об использовании.
Все выборки ограничены владельцем: чужая позиция не находится и даёт 404.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from backend.api.deps import Catalogs, CurrentUser, Products, Settings
from backend.api.schemas import (
    ProductCreate,
    ProductRead,
    ProductStatusUpdate,
    ProductUpdate,
)
from backend.core.urgency import urgency_level
from backend.db.models import Product, ProductStatusCode
from backend.repositories.products import DuplicateProductError

router = APIRouter(prefix="/products", tags=["products"])

StatusFilter = Literal["in_stock", "used", "written_off", "removed", "all"]


def to_read(product: Product, horizon_days: int, today: date) -> ProductRead:
    """Модель в схему ответа с расчётом остаточного срока и цвета."""
    days_left = (product.expiry_date - today).days
    return ProductRead(
        id=product.id,
        name=product.name,
        expiry_date=product.expiry_date,
        manufacture_date=product.manufacture_date,
        ingredient_name=product.ingredient_name,
        storage_place_id=product.storage_place_id,
        status_code=product.status_code,
        quantity=float(product.quantity),
        unit=product.unit,
        days_left=days_left,
        urgency=urgency_level(days_left, horizon_days),
    )


async def _validate_references(
    catalogs: Catalogs,
    telegram_id: int,
    ingredient_name: str | None,
    storage_place_id: int | None,
) -> None:
    """Проверяет ссылки на справочник и на место хранения владельца."""
    if ingredient_name is not None and not await catalogs.ingredient_exists(
        ingredient_name
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ингредиента «{ingredient_name}» нет в справочнике",
        )
    if storage_place_id is not None and not await catalogs.get_storage_place(
        telegram_id, storage_place_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Место хранения не найдено",
        )


async def _get_owned(products: Products, telegram_id: int, product_id: int) -> Product:
    """Продукт пользователя или 404.

    Для чужой записи ответ такой же, как для несуществующей: 403 подтвердил
    бы, что позиция с таким идентификатором есть.
    """
    product = await products.get_by_id(telegram_id, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Продукт не найден"
        )
    return product


@router.get("", response_model=list[ProductRead])
async def list_products(
    user: CurrentUser,
    products: Products,
    settings: Settings,
    status_filter: Annotated[StatusFilter, Query(alias="status")] = "in_stock",
) -> list[ProductRead]:
    """Перечень продуктов пользователя.

    По умолчанию — только то, что есть в наличии. Использованное,
    списанное и удалённое из перечня доступно через параметр status:
    записи не стираются, история операций сохраняется.
    """
    user_settings = await settings.get(user.telegram_id)
    items = await products.get_all(
        user.telegram_id, None if status_filter == "all" else status_filter
    )
    today = date.today()
    return [to_read(item, user_settings.horizon_days, today) for item in items]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user: CurrentUser,
    products: Products,
    catalogs: Catalogs,
    settings: Settings,
) -> ProductRead:
    """Добавление продукта.

    Ингредиент из справочника обязателен: вариант «сохранить без
    ингредиента» не поддерживается, такой продукт не участвовал бы
    в подборе при α = 1. Категория отдельно не вводится — она выводится
    из ингредиента.
    """
    await _validate_references(
        catalogs, user.telegram_id, payload.ingredient_name, payload.storage_place_id
    )
    user_settings = await settings.get(user.telegram_id)
    try:
        product = await products.create(user.telegram_id, payload.model_dump())
    except DuplicateProductError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Такой продукт с этим сроком годности уже добавлен",
        ) from error
    return to_read(product, user_settings.horizon_days, date.today())


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    user: CurrentUser,
    products: Products,
    catalogs: Catalogs,
    settings: Settings,
) -> ProductRead:
    """Редактирование продукта: меняются только переданные поля."""
    product = await _get_owned(products, user.telegram_id, product_id)
    fields = payload.model_dump(exclude_unset=True)

    await _validate_references(
        catalogs,
        user.telegram_id,
        fields.get("ingredient_name"),
        fields.get("storage_place_id"),
    )

    expiry_date = fields.get("expiry_date", product.expiry_date)
    manufacture_date = fields.get("manufacture_date", product.manufacture_date)
    if manufacture_date and expiry_date < manufacture_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Срок годности раньше даты изготовления",
        )

    user_settings = await settings.get(user.telegram_id)
    try:
        product = await products.update(product, fields)
    except DuplicateProductError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Такой продукт с этим сроком годности уже добавлен",
        ) from error
    return to_read(product, user_settings.horizon_days, date.today())


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int, user: CurrentUser, products: Products
) -> Response:
    """Удаление продукта из перечня.

    Физически запись не удаляется: продукту проставляется статус «удалён»,
    иначе оборвалась бы история операций и ссылки из журнала уведомлений.
    Из перечня в наличии позиция при этом пропадает.

    Именно ``removed``, а не ``written_off``: списание означает реальные
    пищевые потери и попадает в статистику третьей главы, а удаление —
    это ошибочно внесённая позиция, потерями она не является. Смешивать
    их одним статусом нельзя, статистика потерь была бы завышена.
    """
    product = await _get_owned(products, user.telegram_id, product_id)
    await products.set_status(product, ProductStatusCode.REMOVED)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{product_id}/status", response_model=ProductRead)
async def set_product_status(
    product_id: int,
    payload: ProductStatusUpdate,
    user: CurrentUser,
    products: Products,
    settings: Settings,
) -> ProductRead:
    """Отметка «использован» или «списан»."""
    product = await _get_owned(products, user.telegram_id, product_id)
    user_settings = await settings.get(user.telegram_id)
    product = await products.set_status(product, payload.status_code)
    return to_read(product, user_settings.horizon_days, date.today())
