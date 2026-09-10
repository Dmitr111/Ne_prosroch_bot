"""Точка входа FastAPI.

Создаёт приложение, подключает роутеры (products, catalogs, recommendations,
settings), настраивает CORS для mini app и управляет жизненным циклом
подключения к БД и планировщика.

Планировщик поднимается здесь же, в lifespan: отдельного процесса под него
не заводим. Бот для рассылки создаётся свой — поллинг ведёт отдельный
процесс ``python -m backend.bot.main``, а отправке сообщений он не нужен.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import catalogs, products, recommendations
from backend.api import settings as settings_api
from backend.bot.main import create_bot
from backend.config import settings
from backend.db.session import engine
from backend.scheduler.jobs import create_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Поднимает планировщик на время жизни приложения."""
    logging.basicConfig(level=settings.log_level)

    bot = create_bot()
    scheduler = create_scheduler(bot)
    scheduler.start()
    logger.info(
        "планировщик запущен (%s): рассылка ежечасно, списание в %s",
        settings.timezone,
        settings.daily_check_time.strftime("%H:%M"),
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await engine.dispose()


app = FastAPI(title="Не просрочь", lifespan=lifespan)

# Mini app открывается с домена Telegram, поэтому запросы к API идут
# с другого источника; перечень задаётся переменной CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(catalogs.router)
app.include_router(recommendations.router)
app.include_router(settings_api.router)
