"""Тесты жадного подбора рецептов.

Проверяется постановка из раздела 1.4: максимизировать V(S) = Σ wᵢ
по объединению покрытых продуктов при |S| ≤ k, отбирая рецепты жадно.
"""

import pytest

from backend.core.greedy import GreedyRecommender, Product, Recipe, coverage_value


def product(product_id: int, ingredient_name: str) -> Product:
    return Product(id=product_id, ingredient_name=ingredient_name)


def recipe(title: str, *ingredient_names: str) -> Recipe:
    return Recipe(title=title, ingredient_names=frozenset(ingredient_names))


def test_shared_product_counted_once() -> None:
    """Полезность считается по объединению, а не суммированием по рецептам.

    Молоко входит в оба рецепта, но расходуется один раз, поэтому
    V({A, B}) = 5 + 3 + 1 = 9, а не 8 + 6 = 14.
    """
    milk = product(1, "молоко")
    egg = product(2, "куриное яйцо")
    flour = product(3, "мука")
    weights = {milk: 5, egg: 3, flour: 1}

    omelette = recipe("Омлет", "молоко", "куриное яйцо")
    pancakes = recipe("Блины", "молоко", "мука")

    selected = GreedyRecommender.recommend([omelette, pancakes], weights, k=2)

    assert selected == [omelette, pancakes]
    assert coverage_value(selected, weights) == 9


def test_second_recipe_adds_only_its_new_products() -> None:
    """Прирост второго шага считается без уже покрытых продуктов.

    Рецепт с большей суммой весов по составу может дать меньший прирост,
    если его продукты уже покрыты, — проверяем, что выбирается не он.
    """
    milk = product(1, "молоко")
    egg = product(2, "куриное яйцо")
    flour = product(3, "мука")
    potato = product(4, "картофель")
    weights = {milk: 10, egg: 10, flour: 2, potato: 3}

    omelette = recipe("Омлет", "молоко", "куриное яйцо")
    # Сумма весов по составу 12, но молоко уже покрыто омлетом: прирост 2
    pancakes = recipe("Блины", "молоко", "мука")
    # Сумма весов по составу 3, продукт свободен: прирост 3
    potatoes = recipe("Картошка", "картофель")

    selected = GreedyRecommender.recommend([omelette, pancakes, potatoes], weights, k=2)

    assert selected == [omelette, potatoes]
    assert coverage_value(selected, weights) == 23


def test_no_products_gives_empty_selection() -> None:
    """Пустой перечень запасов — рекомендовать нечего."""
    recipes = [recipe("Омлет", "молоко", "куриное яйцо")]

    assert GreedyRecommender.recommend(recipes, {}, k=5) == []


def test_all_weights_zero_gives_empty_selection() -> None:
    """Нулевой прирост прерывает отбор: срочных продуктов нет."""
    weights = {product(1, "молоко"): 0, product(2, "куриное яйцо"): 0}
    recipes = [
        recipe("Омлет", "молоко", "куриное яйцо"),
        recipe("Молочный коктейль", "молоко"),
    ]

    assert GreedyRecommender.recommend(recipes, weights, k=5) == []


def test_stops_when_further_recipes_add_nothing() -> None:
    """Отбор прерывается на нулевом приросте, а не добирает до k."""
    milk = product(1, "молоко")
    weights = {milk: 4}
    first = recipe("Молочный коктейль", "молоко")
    second = recipe("Молоко с мёдом", "молоко")

    selected = GreedyRecommender.recommend([first, second], weights, k=5)

    assert selected == [first]


def test_fewer_recipes_than_k() -> None:
    """Рецептов меньше k — возвращаются все полезные, без ошибок."""
    milk = product(1, "молоко")
    potato = product(2, "картофель")
    weights = {milk: 3, potato: 2}
    recipes = [recipe("Коктейль", "молоко"), recipe("Пюре", "картофель")]

    selected = GreedyRecommender.recommend(recipes, weights, k=10)

    assert len(selected) == 2
    assert coverage_value(selected, weights) == 5


def test_selection_limited_by_k() -> None:
    """Размер набора не превышает k, даже когда полезных рецептов больше."""
    weights = {
        product(1, "молоко"): 5,
        product(2, "картофель"): 4,
        product(3, "мука"): 3,
    }
    recipes = [
        recipe("Коктейль", "молоко"),
        recipe("Пюре", "картофель"),
        recipe("Лепёшки", "мука"),
    ]

    selected = GreedyRecommender.recommend(recipes, weights, k=2)

    assert len(selected) == 2
    # Жадный алгоритм берёт самые полезные: молоко (5) и картофель (4)
    assert coverage_value(selected, weights) == 9


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_gives_empty_selection(k: int) -> None:
    weights = {product(1, "молоко"): 5}

    assert GreedyRecommender.recommend([recipe("Коктейль", "молоко")], weights, k=k) == []


def test_uncovered_product_does_not_break_value() -> None:
    """Продукт, которого нет ни в одном рецепте, не искажает полезность.

    В справочнике такие есть: чай и кофе не входят в состав ни одного
    рецепта, но лежат в запасах и получают вес наравне с остальными.
    """
    milk = product(1, "молоко")
    tea = product(2, "чай")
    coffee = product(3, "кофе")
    weights = {milk: 4, tea: 9, coffee: 8}

    selected = GreedyRecommender.recommend([recipe("Коктейль", "молоко")], weights, k=3)

    assert selected == [recipe("Коктейль", "молоко")]
    # Учитывается только покрытое молоко, веса чая и кофе в V(S) не попадают
    assert coverage_value(selected, weights) == 4


def test_recipe_with_missing_ingredient_is_not_applicable() -> None:
    """При α = 1 рецепт годится, только если есть все его ингредиенты."""
    milk = product(1, "молоко")
    weights = {milk: 5}
    incomplete = recipe("Омлет", "молоко", "куриное яйцо")
    complete = recipe("Коктейль", "молоко")

    selected = GreedyRecommender.recommend([incomplete, complete], weights, k=5)

    assert selected == [complete]


def test_several_products_with_same_ingredient_all_covered() -> None:
    """Две пачки молока с разными сроками — два продукта, оба покрываются.

    Позиции запасов различаются по сроку годности, поэтому вес считается
    по каждой, а не по типовому ингредиенту.
    """
    fresh_milk = product(1, "молоко")
    expiring_milk = product(2, "молоко")
    weights = {fresh_milk: 1, expiring_milk: 6}

    selected = GreedyRecommender.recommend([recipe("Коктейль", "молоко")], weights, k=1)

    assert len(selected) == 1
    assert coverage_value(selected, weights) == 7


def test_no_recipes_gives_empty_selection() -> None:
    assert GreedyRecommender.recommend([], {product(1, "молоко"): 5}, k=3) == []


def test_recipes_are_ordered_by_selection_step() -> None:
    """Порядок результата — порядок отбора, то есть убывания прироста."""
    weights = {
        product(1, "молоко"): 2,
        product(2, "картофель"): 7,
        product(3, "мука"): 4,
    }
    recipes = [
        recipe("Коктейль", "молоко"),
        recipe("Пюре", "картофель"),
        recipe("Лепёшки", "мука"),
    ]

    selected = GreedyRecommender.recommend(recipes, weights, k=3)

    assert [item.title for item in selected] == ["Пюре", "Лепёшки", "Коктейль"]


def test_recommender_is_stateless() -> None:
    """Ни k, ни горизонт в полях не хранятся — вызовы независимы."""
    weights = {product(1, "молоко"): 5, product(2, "картофель"): 4}
    recipes = [recipe("Коктейль", "молоко"), recipe("Пюре", "картофель")]

    assert GreedyRecommender().__dict__ == {}
    assert len(GreedyRecommender.recommend(recipes, weights, k=1)) == 1
    assert len(GreedyRecommender.recommend(recipes, weights, k=2)) == 2
    assert len(GreedyRecommender.recommend(recipes, weights, k=1)) == 1


def test_input_collections_are_not_modified() -> None:
    """Алгоритм не портит переданные ему структуры."""
    weights = {product(1, "молоко"): 5, product(2, "картофель"): 4}
    recipes = [recipe("Коктейль", "молоко"), recipe("Пюре", "картофель")]
    weights_before = dict(weights)
    recipes_before = list(recipes)

    GreedyRecommender.recommend(recipes, weights, k=2)

    assert weights == weights_before
    assert recipes == recipes_before


def test_coverage_value_of_empty_selection() -> None:
    assert coverage_value([], {product(1, "молоко"): 5}) == 0
