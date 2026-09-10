"""Точка входа Telegram-бота на aiogram.

Создаёт Bot и Dispatcher, обрабатывает /start и отдаёт кнопку открытия
mini app, запускает поллинг.

Работает через long polling: вебхук не разворачивается, публичный HTTPS
нужен только самому mini app. Запуск отдельным процессом:
``python -m backend.bot.main``. Планировщик живёт в процессе FastAPI
и создаёт для отправки собственный экземпляр Bot — поллинг ему не нужен.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from backend.config import settings

logger = logging.getLogger(__name__)

router = Router()

WELCOME_TEXT = (
    "Не просрочь — помогает следить за сроками годности домашних запасов.\n\n"
    "Добавьте продукты, и бот напомнит, когда что-то начнёт портиться, "
    "и подскажет, что из этого приготовить."
)


def create_bot() -> Bot:
    """Создаёт клиент Telegram по токену из настроек.

    Разметка сообщений не включается: наименования продуктов вводит
    пользователь, и любой символ разметки в них ломал бы отправку.
    """
    return Bot(token=settings.bot_token)


def build_webapp_keyboard(
    text: str = "Открыть приложение", path: str = ""
) -> InlineKeyboardMarkup:
    """Кнопка запуска mini app.

    :param path: путь внутри приложения, например ``recommendations``
    """
    url = settings.webapp_url.rstrip("/")
    if path:
        url = f"{url}/{path.lstrip('/')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]]
    )


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Приветствие и кнопка запуска mini app."""
    await message.answer(WELCOME_TEXT, reply_markup=build_webapp_keyboard())


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def main() -> None:
    """Запускает поллинг до остановки процесса."""
    logging.basicConfig(level=settings.log_level)
    bot = create_bot()
    dispatcher = create_dispatcher()
    try:
        logger.info("бот запущен, поллинг")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
