"""Замер времени подбора на предельных объёмах — таблица 3.6.2 курсовой.

Нефункциональное требование 5: рекомендации формируются не более чем
за 1 секунду при 100 продуктах и 500 рецептах. Замер в трёх точках:
25 продуктов / 100 рецептов, 50 / 250, 100 / 500.

Замеряется RecommendationService.get_recommendations целиком — перевод
моделей в структуры алгоритма, расчёт весов срочности, фильтр
применимости, жадный отбор и предельное покрытие — с репозиториями
в памяти. Обращений к базе и сети нет: оценивается сам модуль подбора.

Входы строятся под худший случай для алгоритма: рецепты составляются
только из ингредиентов, которые есть в запасах, поэтому при α = 1
применимы все рецепты и жадный отбор перебирает их полностью. В реальных
данных условие α = 1 отсекает большую часть рецептов ещё до отбора,
так что фактическое время меньше замеренного.

Запуск из корня проекта, на сервере:

    venv/bin/python -m tests.benchmark

Результат печатается вместе с конфигурацией машины и сохраняется
в tests/results/benchmark.csv и benchmark.txt.
"""

import asyncio
import csv
import os
import platform
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# Запуск как `python tests/benchmark.py`: корень проекта в путь поиска модулей
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.service import RecommendationService  # noqa: E402

# ---------------------------------------------------------------------------
# Параметры замера
# ---------------------------------------------------------------------------

# (продуктов, рецептов) — точки таблицы 3.6.2
POINTS = ((25, 100), (50, 250), (100, 500))
RUNS = 30
# Прогревочные прогоны не учитываются: первый вызов платит за импорт
# и заполнение кешей интерпретатора
WARMUP = 3
HORIZON = 7
# Значение k по умолчанию в приложении
K = 5
DAYS_LEFT_RANGE = (-2, 10)
# Размер справочника ингредиентов, как в seed.py
INGREDIENT_COUNT = 60
SEED = 20250910
# Порог нефункционального требования 5, мс
LIMIT_MS = 1000

RESULTS_DIR = Path(__file__).parent / "results"
TODAY = date(2026, 3, 10)


# ---------------------------------------------------------------------------
# Данные и репозитории в памяти
# ---------------------------------------------------------------------------


@dataclass
class ProductRow:
    id: int
    ingredient_name: str
    expiry_date: date


@dataclass
class LinkRow:
    ingredient_name: str


@dataclass
class RecipeRow:
    title: str
    ingredients: list[LinkRow]


@dataclass
class SettingsRow:
    horizon_days: int = HORIZON
    recommend_limit: int = K


class MemoryProducts:
    def __init__(self, rows: list[ProductRow]) -> None:
        self._rows = rows

    async def get_active(self, telegram_id: int) -> list[ProductRow]:
        return self._rows


class MemoryRecipes:
    def __init__(self, rows: list[RecipeRow]) -> None:
        self._rows = rows

    async def get_all(self) -> list[RecipeRow]:
        return self._rows


class MemorySettings:
    async def get(self, telegram_id: int) -> SettingsRow:
        return SettingsRow()


class DiscardRecommendations:
    """Сохранение сеанса подбора — запись в БД, в замер она не входит."""

    async def save(self, **kwargs: object) -> None:
        return None


def ingredient_pool() -> tuple[list[str], list[float]]:
    """Справочник с перекосом популярности, как в реальном: лук и яйца
    встречаются часто, горчица — редко. Вес убывает с номером ингредиента."""
    names = [f"ингредиент {number:02d}" for number in range(1, INGREDIENT_COUNT + 1)]
    weights = [1 / rank**0.8 for rank in range(1, INGREDIENT_COUNT + 1)]
    return names, weights


def generate(
    rng: random.Random, product_count: int, recipe_count: int
) -> tuple[list[ProductRow], list[RecipeRow]]:
    """Запасы и рецепты, все рецепты которых применимы при α = 1."""
    names, weights = ingredient_pool()

    products = [
        ProductRow(
            id=number,
            ingredient_name=rng.choices(names, weights)[0],
            expiry_date=TODAY + timedelta(days=rng.randint(*DAYS_LEFT_RANGE)),
        )
        for number in range(1, product_count + 1)
    ]

    # Состав рецептов — только из того, что есть в запасах: худший случай
    stock = sorted({product.ingredient_name for product in products})
    stock_weights = [weights[names.index(name)] for name in stock]
    recipes = []
    for number in range(1, recipe_count + 1):
        size = min(rng.randint(3, 6), len(stock))
        chosen: set[str] = set()
        while len(chosen) < size:
            chosen.add(rng.choices(stock, stock_weights)[0])
        recipes.append(
            RecipeRow(
                title=f"Рецепт {number:04d}",
                ingredients=[LinkRow(name) for name in sorted(chosen)],
            )
        )
    return products, recipes


# ---------------------------------------------------------------------------
# Замер
# ---------------------------------------------------------------------------


async def measure_once(products: list[ProductRow], recipes: list[RecipeRow]) -> float:
    """Время одного вызова подбора в миллисекундах."""
    service = RecommendationService(
        products=MemoryProducts(products),
        recipes=MemoryRecipes(recipes),
        settings=MemorySettings(),
        recommendations=DiscardRecommendations(),
    )
    started = time.perf_counter()
    await service.get_recommendations(1, today=TODAY)
    return (time.perf_counter() - started) * 1000


async def measure_point(point_index: int, product_count: int, recipe_count: int) -> list[float]:
    timings = []
    for run in range(-WARMUP, RUNS):
        # Свой seed на прогон: каждый вход воспроизводится отдельно
        rng = random.Random(SEED + 1000 * point_index + run)
        products, recipes = generate(rng, product_count, recipe_count)
        elapsed = await measure_once(products, recipes)
        if run >= 0:
            timings.append(elapsed)
    return timings


def machine() -> str:
    """Конфигурация машины для подписи к таблице."""
    cpu = platform.processor() or platform.machine()
    memory = "неизвестно"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal"):
                memory = f"{int(line.split()[1]) // 1024} МБ"
                break
    cores = (
        len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    )
    return (
        f"Процессор: {cpu}\n"
        f"Доступно ядер: {cores}\n"
        f"Память: {memory}\n"
        f"ОС: {platform.platform()}\n"
        f"Python: {platform.python_version()}"
    )


async def main() -> None:
    rows = []
    for index, (product_count, recipe_count) in enumerate(POINTS):
        timings = await measure_point(index, product_count, recipe_count)
        rows.append(
            {
                "products": product_count,
                "recipes": recipe_count,
                "runs": len(timings),
                "mean_ms": statistics.fmean(timings),
                "median_ms": statistics.median(timings),
                "max_ms": max(timings),
            }
        )

    lines = [
        "Замер времени подбора (таблица 3.6.2)",
        machine(),
        f"Параметры: T = {HORIZON}, k = {K}, прогонов на точку {RUNS} "
        f"(+{WARMUP} прогревочных), все рецепты применимы",
        "",
        f"{'Продуктов':>9}  {'Рецептов':>8}  {'Среднее, мс':>11}  "
        f"{'Медиана, мс':>11}  {'Максимум, мс':>12}",
    ]
    for row in rows:
        lines.append(
            f"{row['products']:>9}  {row['recipes']:>8}  {row['mean_ms']:>11.2f}  "
            f"{row['median_ms']:>11.2f}  {row['max_ms']:>12.2f}"
        )
    worst = max(row["max_ms"] for row in rows)
    verdict = "выполнено" if worst <= LIMIT_MS else "НЕ выполнено"
    lines += ["", f"Требование ≤ {LIMIT_MS} мс: {verdict}, худший прогон {worst:.2f} мс"]

    report = "\n".join(lines)
    print(report)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "benchmark.txt").write_text(report + "\n", encoding="utf-8")
    with (RESULTS_DIR / "benchmark.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: f"{value:.3f}" if isinstance(value, float) else value
                 for key, value in row.items()}
            )


if __name__ == "__main__":
    asyncio.run(main())
