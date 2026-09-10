"""GreedyRecommender — жадный подбор набора рецептов.

Задача о максимальном покрытии с весами (раздел 1.4): выбрать набор
рецептов S, |S| ≤ k, максимизирующий

    V(S) = Σ wᵢ по pᵢ ∈ ⋃ Pⱼ

где Pⱼ = Iⱼ ∩ P — продукты пользователя, покрываемые рецептом j.
Полезность считается по **объединению** покрытых продуктов: продукт,
входящий в несколько выбранных рецептов, расходуется один раз и в сумму
входит один раз. Складывать полезности рецептов нельзя.

На каждом шаге берётся рецепт с наибольшим приростом полезности; отбор
прерывается, когда лучший прирост равен нулю. Гарантия 1 − 1/e ≈ 0,63,
сложность O(k·m·n).

Рецепт применим, если покрыт полностью: |Pⱼ| / |Iⱼ| ≥ α при α = 1.
Количество продукта не учитывается — продукт либо есть, либо нет.

Модуль работает на собственных структурах и не знает ни о БД, ни о моделях
SQLAlchemy: сопоставление строк таблиц с Product и Recipe — забота
вызывающего слоя.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

# Доля покрытых ингредиентов, при которой рецепт считается применимым.
# В приложении предлагаются только полностью обеспеченные рецепты
ALPHA = 1.0


@dataclass(frozen=True, slots=True)
class Product:
    """Позиция запасов: идентичность позиции и её типовой ингредиент.

    Продуктов с одним ингредиентом может быть несколько — например, две
    пачки молока с разными сроками годности. Это разные позиции с разными
    весами, поэтому ключ — ``id``, а не наименование ингредиента.
    """

    id: int
    ingredient_name: str


@dataclass(frozen=True, slots=True)
class Recipe:
    """Рецепт и множество Iⱼ его ингредиентов."""

    title: str
    ingredient_names: frozenset[str]


def applicable_recipes(
    recipes: Iterable[Recipe], weights: Mapping[Product, int]
) -> list[Recipe]:
    """Рецепты, применимые при α = 1: все ингредиенты есть в запасах.

    Рецепт без состава отбрасывается — отношение |Pⱼ| / |Iⱼ| для него
    не определено. Вынесено отдельно, чтобы точный перебор в эксперименте
    третьей главы отбирал кандидатов ровно тем же кодом, что и жадный:
    иначе сравнивались бы алгоритмы на разных множествах.
    """
    available = {product.ingredient_name for product in weights}
    return [
        recipe
        for recipe in recipes
        if recipe.ingredient_names and recipe.ingredient_names <= available
    ]


def coverage_value(recipes: Iterable[Recipe], weights: Mapping[Product, int]) -> int:
    """Полезность набора V(S) по объединению покрываемых продуктов.

    Нужна для тестов и для эксперимента третьей главы, где полезность
    жадного набора сравнивается с полезностью точного.
    """
    covered_ingredients = {name for recipe in recipes for name in recipe.ingredient_names}
    return sum(
        weight
        for product, weight in weights.items()
        if product.ingredient_name in covered_ingredients
    )


def marginal_coverage(
    selection: Sequence[Recipe], weights: Mapping[Product, int]
) -> list[list[Product]]:
    """Продукты, впервые покрытые каждым рецептом на своём шаге.

    Набор разбирается в том же порядке, в каком его отобрал жадный
    алгоритм: продукт, покрытый предыдущим рецептом, следующему уже
    не засчитывается. Поэтому списки не пересекаются, а их объединение
    даёт ⋃ Pⱼ — то самое множество, по которому считается V(S).

    Нужна интерфейсу: рецепт показывает, какие именно продукты он спасает,
    и эти же продукты списываются по кнопке. Считать пересечение заново
    на клиенте нельзя — там нет ни весов, ни порядка отбора.
    """
    products_by_ingredient: dict[str, list[Product]] = defaultdict(list)
    for product in weights:
        products_by_ingredient[product.ingredient_name].append(product)

    coverage: list[list[Product]] = []
    covered: set[Product] = set()
    for recipe in selection:
        newly_covered = [
            product
            for name in sorted(recipe.ingredient_names)
            for product in products_by_ingredient[name]
            if product not in covered
        ]
        coverage.append(newly_covered)
        covered.update(newly_covered)
    return coverage


def marginal_gains(
    selection: Sequence[Recipe], weights: Mapping[Product, int]
) -> list[int]:
    """Прирост полезности, который дал каждый рецепт на своём шаге.

    Сумма приростов равна V(S). Нужна, чтобы записать covered_weight
    в recommendation_items, не меняя сигнатуру
    ``GreedyRecommender.recommend`` из курсовой.
    """
    return [
        sum(weights[product] for product in covered)
        for covered in marginal_coverage(selection, weights)
    ]


class GreedyRecommender:
    """Жадный отбор рецептов под ограничение |S| ≤ k."""

    @staticmethod
    def recommend(
        recipes: Sequence[Recipe],
        weights: Mapping[Product, int],
        k: int,
    ) -> list[Recipe]:
        """Отбирает не более k рецептов, максимизируя покрытие срочных продуктов.

        :param recipes: рецепты-кандидаты
        :param weights: веса срочности по позициям запасов; ключи задают
            множество продуктов пользователя P
        :param k: максимальный размер набора
        :return: отобранные рецепты в порядке отбора, то есть в порядке
            убывания прироста полезности
        """
        if k <= 0 or not weights or not recipes:
            return []

        products_by_ingredient: dict[str, list[Product]] = defaultdict(list)
        for product in weights:
            products_by_ingredient[product.ingredient_name].append(product)

        candidates = applicable_recipes(recipes, weights)

        selected: list[Recipe] = []
        covered: set[Product] = set()

        while candidates and len(selected) < k:
            best: Recipe | None = None
            best_gain = 0

            for recipe in candidates:
                gain = sum(
                    weights[product]
                    for name in recipe.ingredient_names
                    for product in products_by_ingredient[name]
                    if product not in covered
                )
                if gain > best_gain:
                    best, best_gain = recipe, gain

            # Прирост исчерпан: оставшиеся рецепты ничего нового не покрывают
            if best is None:
                break

            selected.append(best)
            candidates.remove(best)
            covered.update(
                product
                for name in best.ingredient_names
                for product in products_by_ingredient[name]
            )

        return selected
