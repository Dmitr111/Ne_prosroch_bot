"""Эндпоинты пользовательских настроек.

Параметры напоминаний и подбора: время рассылки, порог срочности,
горизонт планирования T и ограничение k на размер набора рецептов.
"""

from fastapi import APIRouter

from backend.api.deps import CurrentUser, Settings
from backend.api.schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def to_read(settings) -> SettingsRead:
    return SettingsRead(
        notify_time=settings.notify_time,
        threshold_days=settings.threshold_days,
        horizon_days=settings.horizon_days,
        recommend_limit=settings.recommend_limit,
    )


@router.get("", response_model=SettingsRead)
async def read_settings(user: CurrentUser, settings: Settings) -> SettingsRead:
    """Текущие параметры; при первом обращении заводятся значения по умолчанию."""
    return to_read(await settings.get(user.telegram_id))


@router.patch("", response_model=SettingsRead)
async def update_settings(
    payload: SettingsUpdate, user: CurrentUser, settings: Settings
) -> SettingsRead:
    """Изменение параметров: меняются только переданные поля."""
    current = await settings.get(user.telegram_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields:
        current = await settings.update(current, fields)
    return to_read(current)
