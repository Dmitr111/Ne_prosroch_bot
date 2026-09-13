"""Общее время приложения, независимо от часового пояса ОС."""

from datetime import datetime
from zoneinfo import ZoneInfo


def application_now(now: datetime | None = None) -> datetime:
    """Возвращает текущий или переданный момент в настроенном часовом поясе."""
    # Отложенный импорт: сервис с явным today проверяется без .env.
    from backend.config import settings

    local_zone = ZoneInfo(settings.timezone)
    if now is None:
        return datetime.now(tz=local_zone)
    return now.astimezone(local_zone)
