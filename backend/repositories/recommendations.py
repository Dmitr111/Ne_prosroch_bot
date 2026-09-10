"""Репозиторий сеансов подбора.

Сохраняет условия запуска подбора и его результат: действовавшие T и k,
источник запуска, отобранные рецепты с позицией и приростом полезности.
Нужен для эксперимента третьей главы — по этим записям восстанавливается,
на каких параметрах получен каждый набор.
"""

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import RecommendationItem, RecommendationSession


class RecommendationRepository:
    """Запись сеансов подбора и их состава."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        telegram_id: int,
        trigger: str,
        horizon_days: int,
        k: int,
        items: Sequence[tuple[str, int]],
    ) -> RecommendationSession:
        """Сохраняет сеанс подбора вместе с отобранными рецептами.

        :param items: пары «наименование рецепта, прирост полезности»
            в порядке отбора; позиция проставляется по порядку, с единицы
        :return: созданный сеанс

        Пустой набор тоже сохраняется: то, что подбор запускался и ничего
        не нашёл, — самостоятельный результат для эксперимента.

        Момент создания проставляется здесь, а не значением по умолчанию
        в схеме: ``now()`` в PostgreSQL возвращает время начала транзакции
        и одинаков для всех записей внутри неё, а на паре
        (telegram_id, created_at) стоит UNIQUE.
        """
        recommendation_session = RecommendationSession(
            telegram_id=telegram_id,
            created_at=datetime.now(tz=timezone.utc),
            trigger=trigger,
            horizon_days=horizon_days,
            k=k,
        )
        self._session.add(recommendation_session)
        await self._session.flush()

        for position, (recipe_title, covered_weight) in enumerate(items, start=1):
            self._session.add(
                RecommendationItem(
                    session_id=recommendation_session.id,
                    recipe_title=recipe_title,
                    position=position,
                    covered_weight=covered_weight,
                )
            )
        await self._session.flush()

        return recommendation_session
