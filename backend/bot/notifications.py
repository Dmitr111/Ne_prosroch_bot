"""Формирование и отправка напоминаний.

Собирает текст уведомления о продуктах с истекающим сроком годности и
рекомендованных рецептах, отправляет его пользователю и фиксирует факт
отправки.

Формирование текста отделено от отправки: ``format_expiry_message``
работает на обычных объектах с нужными атрибутами и проверяется тестами
без Telegram и без БД.
"""

import logging
from collections.abc import Sequence
from datetime import date
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from backend.bot.main import build_webapp_keyboard

logger = logging.getLogger(__name__)


class ExpiringProduct(Protocol):
    """Что нужно от продукта для текста напоминания."""

    name: str
    expiry_date: date


class SuggestedRecipe(Protocol):
    """Что нужно от рецепта для текста напоминания."""

    title: str
    cooking_time_min: int | None


NO_RECIPES_TEXT = "Подходящих рецептов из этих продуктов не нашлось."


def _days_phrase(days: int) -> str:
    """Человекочитаемый остаточный срок с правильным окончанием."""
    if days == 0:
        return "сегодня"
    if days == 1:
        return "завтра"

    tail = days % 100
    if 11 <= tail <= 14:
        word = "дней"
    elif days % 10 == 1:
        word = "день"
    elif days % 10 in (2, 3, 4):
        word = "дня"
    else:
        word = "дней"
    return f"через {days} {word}"


def format_expiry_message(
    products: Sequence[ExpiringProduct],
    recipes: Sequence[SuggestedRecipe],
    today: date,
) -> str:
    """Текст напоминания о продуктах с истекающим сроком.

    Цветовая индикация та же, что в интерфейсе: красный — истекает
    сегодня, жёлтый — срок приближается. Если рецептов нет, сообщение
    всё равно отправляется: информирование важнее подсказки.
    """
    lines = ["Скоро истекает срок годности:", ""]
    for product in products:
        days_left = (product.expiry_date - today).days
        marker = "🔴" if days_left <= 0 else "🟡"
        lines.append(f"{marker} {product.name} — {_days_phrase(days_left)}")

    lines.append("")
    if recipes:
        lines.append("Что можно приготовить:")
        for recipe in recipes:
            if recipe.cooking_time_min:
                lines.append(f"• {recipe.title} — {recipe.cooking_time_min} мин")
            else:
                lines.append(f"• {recipe.title}")
    else:
        lines.append(NO_RECIPES_TEXT)

    return "\n".join(lines)


async def send_expiry_notification(
    bot: Bot,
    telegram_id: int,
    products: Sequence[ExpiringProduct],
    recipes: Sequence[SuggestedRecipe],
    today: date,
) -> bool:
    """Отправляет напоминание пользователю.

    :return: True, если сообщение доставлено. Ошибка Telegram не должна
        ронять обход остальных пользователей, поэтому она логируется
        и превращается в False — журнал тогда не пишется и напоминание
        повторится на следующем запуске.
    """
    text = format_expiry_message(products, recipes, today)
    keyboard = build_webapp_keyboard(
        text="Что приготовить" if recipes else "Открыть приложение",
        path="recommendations" if recipes else "",
    )
    try:
        await bot.send_message(telegram_id, text, reply_markup=keyboard)
    except TelegramAPIError:
        logger.exception("не удалось отправить напоминание пользователю %s", telegram_id)
        return False
    return True
