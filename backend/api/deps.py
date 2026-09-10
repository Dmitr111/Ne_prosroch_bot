"""Общие зависимости API.

Проверяет подпись Telegram initData по токену бота, извлекает из неё
Telegram-пользователя, находит или создаёт его в БД и отдаёт текущего
пользователя вместе с сессией БД в обработчики.

Проверка подписи по алгоритму Telegram Web Apps: из параметров строки,
кроме ``hash``, собирается строка проверки, ключ выводится из токена бота,
результат сравнивается с переданным ``hash``. Дополнительно проверяется
срок жизни ``auth_date`` — иначе перехваченная строка годилась бы вечно.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.service import RecommendationService
from backend.db.models import User
from backend.db.session import get_session
from backend.repositories.catalogs import CatalogRepository
from backend.repositories.products import ProductRepository
from backend.repositories.recipes import RecipeRepository
from backend.repositories.recommendations import RecommendationRepository
from backend.repositories.settings import SettingsRepository
from backend.repositories.users import UserRepository

logger = logging.getLogger(__name__)

# Сколько времени initData считается свежей
AUTH_TTL = timedelta(hours=24)

# Схема заголовка Authorization, принятая в Telegram Mini Apps
AUTH_SCHEME = "tma"


class InitDataError(Exception):
    """initData отсутствует, повреждена, подделана или просрочена."""


@dataclass(frozen=True)
class TelegramUser:
    """Пользователь, извлечённый из проверенной initData."""

    telegram_id: int
    username: str | None


def _secret_key(bot_token: str) -> bytes:
    """Ключ подписи: HMAC-SHA256 от токена бота с ключом WebAppData."""
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def parse_init_data(
    init_data: str,
    bot_token: str,
    now: datetime | None = None,
    ttl: timedelta = AUTH_TTL,
) -> TelegramUser:
    """Проверяет подпись initData и возвращает пользователя.

    Функция чистая: ни БД, ни настроек, ни запроса — только строка и токен.
    :raises InitDataError: подпись не сошлась, строка испорчена или устарела
    """
    if not init_data:
        raise InitDataError("initData не передана")

    # keep_blank_values: пустые значения тоже участвуют в подписи
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("в initData нет поля hash")

    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    expected_hash = hmac.new(
        _secret_key(bot_token), check_string.encode(), hashlib.sha256
    ).hexdigest()
    # Сравнение постоянного времени: обычное == даёт побитовую утечку
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("подпись initData не сошлась")

    raw_auth_date = pairs.get("auth_date")
    if not raw_auth_date:
        raise InitDataError("в initData нет поля auth_date")
    try:
        auth_date = datetime.fromtimestamp(int(raw_auth_date), tz=timezone.utc)
    except ValueError as error:
        raise InitDataError("некорректное значение auth_date") from error

    now = now or datetime.now(tz=timezone.utc)
    if now - auth_date > ttl:
        raise InitDataError("initData устарела")

    raw_user = pairs.get("user")
    if not raw_user:
        raise InitDataError("в initData нет данных пользователя")
    try:
        user = json.loads(raw_user)
        telegram_id = int(user["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise InitDataError("не удалось разобрать данные пользователя") from error

    return TelegramUser(telegram_id=telegram_id, username=user.get("username"))


def _extract_init_data(
    authorization: str | None, init_data_header: str | None
) -> str | None:
    """Достаёт initData из заголовка Authorization или X-Telegram-Init-Data."""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == AUTH_SCHEME and value:
            return value
    return init_data_header


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
) -> User:
    """Текущий пользователь по проверенной initData.

    Пользователь заводится при первом обращении: отдельной регистрации
    в приложении нет.
    """
    init_data = _extract_init_data(authorization, x_telegram_init_data)
    try:
        telegram_user = parse_init_data(init_data or "", settings.bot_token)
    except InitDataError as error:
        logger.warning("отклонена авторизация: %s", error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось подтвердить подпись Telegram",
            headers={"WWW-Authenticate": AUTH_SCHEME},
        ) from error

    return await UserRepository(session).get_or_create(
        telegram_user.telegram_id, telegram_user.username
    )


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_product_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProductRepository:
    return ProductRepository(session)


def get_catalog_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogRepository:
    return CatalogRepository(session)


def get_settings_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettingsRepository:
    return SettingsRepository(session)


def get_recommendation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RecommendationService:
    return RecommendationService(
        products=ProductRepository(session),
        recipes=RecipeRepository(session),
        settings=SettingsRepository(session),
        recommendations=RecommendationRepository(session),
    )


Products = Annotated[ProductRepository, Depends(get_product_repository)]
Catalogs = Annotated[CatalogRepository, Depends(get_catalog_repository)]
Settings = Annotated[SettingsRepository, Depends(get_settings_repository)]
Recommendations = Annotated[RecommendationService, Depends(get_recommendation_service)]
