"""Точный перебор наборов рецептов — только для эксперимента.

Экспоненциальный поиск оптимального набора по всем подмножествам рецептов.
Не используется в приложении, служит эталоном для оценки качества жадного
алгоритма в третьей главе.

Перебираются все подмножества применимых рецептов мощности от 1 до k,
для каждого считается V(S). Кандидаты отбираются функцией
``applicable_recipes`` из модуля подбора, а полезность — функцией
``coverage_value`` оттуда же: собственной копии формул здесь нет, иначе
расхождение в реализациях выдавалось бы за расхождение алгоритмов.

Число подмножеств растёт как C(m, k), поэтому эксперимент проводится
на наборах малой размерности: 10–15 рецептов, k = 3.
"""

from collections.abc import Mapping, Sequence
from itertools import combinations

from backend.core.greedy import Product, Recipe, applicable_recipes, coverage_value


class ExactRecommender:
    """Точный отбор набора рецептов полным перебором.

    Сигнатура ``recommend`` совпадает с GreedyRecommender, чтобы алгоритмы
    можно было подставлять один вместо другого.
    """

    @staticmethod
    def recommend(
        recipes: Sequence[Recipe],
        weights: Mapping[Product, int],
        k: int,
    ) -> list[Recipe]:
        """Набор мощности не более k с максимальной полезностью V(S).

        При нулевых весах возвращает пустой набор: полезность любого
        подмножества равна нулю, добавлять рецепты незачем.
        """
        if k <= 0 or not weights or not recipes:
            return []

        candidates = applicable_recipes(recipes, weights)

        best_selection: list[Recipe] = []
        best_value = 0

        for size in range(1, min(k, len(candidates)) + 1):
            for combination in combinations(candidates, size):
                value = coverage_value(combination, weights)
                if value > best_value:
                    best_value = value
                    best_selection = list(combination)

        return best_selection
