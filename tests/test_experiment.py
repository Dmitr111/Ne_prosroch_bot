"""Эксперимент третьей главы: жадный алгоритм против точного перебора.

На случайных наборах малой размерности считается отношение
V(жадный) / V(точный). Теоретическая гарантия для жадного алгоритма
на задаче максимального покрытия — 1 − 1/e ≈ 0,632; ожидается, что
на практике отношение окажется заметно выше.

Наборы генерируются с фиксированным seed, поэтому результат
воспроизводится от запуска к запуску. Составы рецептов повторяют
распределение из справочника ``backend/db/seed.py``: несколько популярных
ингредиентов входят во многие рецепты, редкие встречаются однократно.
Часть продуктов не покрывается ни одним рецептом — как чай и кофе
в справочнике.

Подробный вывод и путь к CSV печатаются при запуске с ``-s``:

    pytest tests/test_experiment.py -s
"""

import csv
import random
import statistics
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest

from backend.core.greedy import (
    GreedyRecommender,
    Product,
    Recipe,
    coverage_value,
)
from backend.core.urgency import UrgencyCalculator
from tests.exact import ExactRecommender

# ---------------------------------------------------------------------------
# Параметры эксперимента
# ---------------------------------------------------------------------------

RUNS = 100
RECIPES_RANGE = (10, 15)
PRODUCTS_RANGE = (10, 20)
K = 3
HORIZON = 7
# Остаточный срок годности: отрицательный означает просрочку
DAYS_LEFT_RANGE = (-2, 10)
SEED = 20250909

# Теоретическая гарантия жадного алгоритма на максимальном покрытии
GUARANTEE = 0.632

RESULTS_PATH = Path(__file__).parent / "results" / "experiment.csv"

# Распределение ингредиентов повторяет справочник: популярные входят
# во многие рецепты, редкие — в один-два
POPULAR_INGREDIENTS = (
    "репчатый лук",
    "куриное яйцо",
    "мука",
    "картофель",
    "молоко",
    "сливочное масло",
)
COMMON_INGREDIENTS = (
    "морковь",
    "чеснок",
    "сметана",
    "твёрдый сыр",
    "макароны",
    "рис",
    "помидор",
    "растительное масло",
)
RARE_INGREDIENTS = (
    "кабачок",
    "сельдь",
    "горчица",
    "кетчуп",
    "шоколад",
    "варенье",
    "сгущённое молоко",
    "сливки",
    "дрожжи",
    "пшено",
    "лавровый лист",
    "панировочные сухари",
)
# Продукты, которых нет ни в одном рецепте
UNCOVERED_INGREDIENTS = ("чай", "кофе")


# ---------------------------------------------------------------------------
# Генерация наборов
# ---------------------------------------------------------------------------


class Case(NamedTuple):
    """Случайный набор: рецепты и веса срочности по позициям запасов."""

    recipes: list[Recipe]
    weights: dict[Product, int]


class RunResult(NamedTuple):
    """Итог одного прогона."""

    run: int
    recipes: int
    products: int
    greedy_value: int
    exact_value: int
    ratio: float


def _pick_ingredient(rng: random.Random) -> str:
    """Выбирает ингредиент с перекосом в сторону популярных."""
    roll = rng.random()
    if roll < 0.55:
        return rng.choice(POPULAR_INGREDIENTS)
    if roll < 0.90:
        return rng.choice(COMMON_INGREDIENTS)
    return rng.choice(RARE_INGREDIENTS)


def _make_recipe(rng: random.Random, number: int) -> Recipe:
    """Рецепт из 3–6 различных ингредиентов, как в справочнике."""
    size = rng.randint(3, 6)
    names: set[str] = set()
    while len(names) < size:
        names.add(_pick_ingredient(rng))
    return Recipe(title=f"Рецепт {number}", ingredient_names=frozenset(names))


def _generate_case(rng: random.Random, recipe_count: int | None = None) -> Case:
    """Случайный набор рецептов и запасов.

    Запасы формируются так, чтобы применимые рецепты гарантированно нашлись:
    сначала берутся все ингредиенты двух-трёх случайных рецептов, затем
    перечень добивается произвольными продуктами, включая непокрываемые.
    Без этого при α = 1 значительная часть наборов оказалась бы пустой
    и сравнивать было бы нечего.
    """
    if recipe_count is None:
        recipe_count = rng.randint(*RECIPES_RANGE)
    recipes = [_make_recipe(rng, number) for number in range(1, recipe_count + 1)]

    stocked = rng.sample(recipes, min(rng.randint(2, 3), len(recipes)))
    guaranteed = sorted({name for recipe in stocked for name in recipe.ingredient_names})

    product_count = min(max(rng.randint(*PRODUCTS_RANGE), len(guaranteed)), 20)
    names = list(guaranteed[:product_count])
    while len(names) < product_count:
        if rng.random() < 0.15:
            names.append(rng.choice(UNCOVERED_INGREDIENTS))
        else:
            names.append(_pick_ingredient(rng))

    weights: dict[Product, int] = {}
    for product_id, name in enumerate(names, start=1):
        days_left = rng.randint(*DAYS_LEFT_RANGE)
        weights[Product(id=product_id, ingredient_name=name)] = UrgencyCalculator.weight(
            days_left, HORIZON
        )

    return Case(recipes=recipes, weights=weights)


def _generate_meaningful_case(rng: random.Random, recipe_count: int | None = None) -> Case:
    """Набор, на котором точное решение имеет положительную полезность.

    Вырожденный случай — все продукты с запасом по сроку, веса нулевые —
    возможен, но отношение V(жадный) / V(точный) на нём не определено,
    поэтому такой набор перегенерируется.
    """
    for _ in range(100):
        case = _generate_case(rng, recipe_count)
        if coverage_value(
            ExactRecommender.recommend(case.recipes, case.weights, K), case.weights
        ):
            return case
    raise RuntimeError("не удалось сгенерировать набор с ненулевой полезностью")


# ---------------------------------------------------------------------------
# Прогон
# ---------------------------------------------------------------------------


def _run_experiment() -> list[RunResult]:
    """Выполняет RUNS прогонов на воспроизводимых случайных наборах."""
    results: list[RunResult] = []
    for run in range(1, RUNS + 1):
        # Свой seed на прогон: набор №17 воспроизводится независимо от остальных
        rng = random.Random(SEED + run)
        case = _generate_meaningful_case(rng)

        greedy = GreedyRecommender.recommend(case.recipes, case.weights, K)
        exact = ExactRecommender.recommend(case.recipes, case.weights, K)

        greedy_value = coverage_value(greedy, case.weights)
        exact_value = coverage_value(exact, case.weights)

        results.append(
            RunResult(
                run=run,
                recipes=len(case.recipes),
                products=len(case.weights),
                greedy_value=greedy_value,
                exact_value=exact_value,
                ratio=greedy_value / exact_value,
            )
        )
    return results


def _write_csv(results: list[RunResult]) -> None:
    """Сохраняет прогоны для таблицы и графика в третьей главе."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["run", "recipes", "products", "greedy_value", "exact_value", "ratio"]
        )
        for result in results:
            writer.writerow(
                [
                    result.run,
                    result.recipes,
                    result.products,
                    result.greedy_value,
                    result.exact_value,
                    f"{result.ratio:.6f}",
                ]
            )


def _report(results: list[RunResult]) -> None:
    ratios = [result.ratio for result in results]
    exact_matches = sum(1 for ratio in ratios if ratio == 1.0)

    print()
    print(f"Эксперимент: {len(results)} прогонов, k = {K}, T = {HORIZON}")
    print(f"  среднее      {statistics.fmean(ratios):.4f}")
    print(f"  медиана      {statistics.median(ratios):.4f}")
    print(f"  минимум      {min(ratios):.4f}")
    print(f"  максимум     {max(ratios):.4f}")
    print(
        f"  точное совпадение  {exact_matches} из {len(results)} "
        f"({exact_matches / len(results):.0%})"
    )
    print(f"  теоретическая гарантия 1 − 1/e ≈ {GUARANTEE}")
    print(f"  результаты: {RESULTS_PATH}")


@pytest.fixture(scope="module")
def results() -> Iterator[list[RunResult]]:
    """Прогоняет эксперимент один раз на модуль и сохраняет CSV."""
    data = _run_experiment()
    _write_csv(data)
    _report(data)
    yield data


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------


def test_ratio_never_below_theoretical_guarantee(results: list[RunResult]) -> None:
    """Отношение полезностей не опускается ниже 1 − 1/e ни на одном наборе."""
    worst = min(results, key=lambda result: result.ratio)

    assert worst.ratio >= GUARANTEE, (
        f"прогон {worst.run}: V(жадный) = {worst.greedy_value}, "
        f"V(точный) = {worst.exact_value}, отношение {worst.ratio:.4f}"
    )


def test_greedy_never_beats_exact(results: list[RunResult]) -> None:
    """Точный перебор не может проиграть жадному — иначе ошибка в переборе."""
    for result in results:
        assert result.greedy_value <= result.exact_value, f"прогон {result.run}"


def test_all_runs_completed(results: list[RunResult]) -> None:
    assert len(results) == RUNS
    for result in results:
        assert RECIPES_RANGE[0] <= result.recipes <= RECIPES_RANGE[1]
        assert PRODUCTS_RANGE[0] <= result.products <= PRODUCTS_RANGE[1]


def test_csv_written(results: list[RunResult]) -> None:
    """CSV пригоден для таблицы и графика: заголовок и RUNS строк."""
    with RESULTS_PATH.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == RUNS
    assert rows[0].keys() == {
        "run",
        "recipes",
        "products",
        "greedy_value",
        "exact_value",
        "ratio",
    }
    assert float(rows[0]["ratio"]) == pytest.approx(results[0].ratio, abs=1e-6)


def test_greedy_matches_exact_when_k_covers_all_applicable() -> None:
    """Когда k не меньше числа применимых рецептов, жадный точен.

    Брать нечего сверх того, что уже взято: жадный отбирает все рецепты
    с положительным приростом, а рецепты с нулевым приростом полезности
    не добавляют, поэтому V совпадает с точным.
    """
    for run in range(50):
        rng = random.Random(SEED + run)
        # Рецептов не больше k, значит применимых тоже не больше k
        case = _generate_meaningful_case(rng, recipe_count=K)

        greedy = GreedyRecommender.recommend(case.recipes, case.weights, K)
        exact = ExactRecommender.recommend(case.recipes, case.weights, K)

        assert coverage_value(greedy, case.weights) == coverage_value(
            exact, case.weights
        ), f"набор {run}"
