"""Настройки приложения из переменных окружения.

Собирает параметры подключения к БД, токен Telegram-бота, URL mini app и
параметры алгоритма рекомендаций в единый объект настроек (pydantic-settings),
читаемый из .env.

Единственный источник настроек: остальные модули импортируют готовый
экземпляр ``settings`` и не обращаются к ``os.environ`` напрямую.
"""

from datetime import time

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Параметры приложения, прочитанные из окружения и файла .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # В .env есть переменные только для docker-compose (POSTGRES_*),
        # они не должны ломать разбор настроек
        extra="ignore",
    )

    # ---------- База данных ----------
    # Асинхронный драйвер для приложения: postgresql+asyncpg
    database_url: str
    # Синхронный драйвер для Alembic: postgresql+psycopg.
    # Если не задан, выводится из database_url подменой драйвера
    alembic_database_url: str = ""
    db_echo: bool = False

    # ---------- Telegram ----------
    bot_token: str
    webapp_url: str

    # ---------- Приложение ----------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # ---------- Напоминания и алгоритм ----------
    timezone: str = "Europe/Moscow"
    # Время ежедневного списания просроченных продуктов.
    # К напоминаниям отношения не имеет: время рассылки задаёт сам
    # пользователь в user_settings.notify_time, задача рассылки
    # запускается ежечасно и отбирает тех, у кого совпал час
    daily_check_time: time = time(9, 0)
    # Горизонт планирования T по умолчанию, дней
    urgency_threshold_days: int = 3
    # Значение k по умолчанию — сколько рецептов показывать
    max_recommendations: int = 5

    @model_validator(mode="after")
    def _fill_alembic_url(self) -> "Settings":
        """Выводит синхронный URL для Alembic, если он не задан явно."""
        if not self.alembic_database_url:
            self.alembic_database_url = self.database_url.replace(
                "+asyncpg", "+psycopg"
            )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        """Разбирает список источников CORS, заданный через запятую."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
