"""Тесты весовой функции срочности.

Проверяется формула из раздела 1.4: wᵢ = max(0, T − τᵢ), где τᵢ — остаточный
срок годности в днях, T — горизонт планирования.
"""

import pytest

from backend.core.urgency import UrgencyCalculator


@pytest.mark.parametrize(
    ("days_left", "horizon", "expected"),
    [
        (3, 7, 4),  # внутри горизонта
        (1, 7, 6),
        (6, 7, 1),
        (0, 7, 7),  # истекает сегодня — максимум среди непросроченных
        (7, 7, 0),  # ровно на границе горизонта веса уже нет
        (8, 7, 0),  # за горизонтом
        (30, 7, 0),
        (2, 3, 1),  # горизонт берётся из настроек, не зашит в функцию
        (2, 14, 12),
    ],
)
def test_weight_matches_formula(days_left: int, horizon: int, expected: int) -> None:
    assert UrgencyCalculator.weight(days_left, horizon) == expected


def test_weight_is_never_negative() -> None:
    """За горизонтом вес обнуляется, а не уходит в минус."""
    for days_left in range(0, 40):
        assert UrgencyCalculator.weight(days_left, 7) >= 0


def test_zero_days_left_gives_horizon() -> None:
    """Продукт, истекающий сегодня, весит ровно T."""
    for horizon in (1, 3, 7, 14, 30):
        assert UrgencyCalculator.weight(0, horizon) == horizon


def test_expired_product_outweighs_any_valid_one() -> None:
    """Просроченный продукт важнее любого непросроченного.

    При τ < 0 формула даёт вес больше T — так просрочка поднимается
    в подборе выше продукта, у которого срок истекает сегодня.
    """
    horizon = 7
    expired = UrgencyCalculator.weight(-2, horizon)
    today = UrgencyCalculator.weight(0, horizon)

    assert expired == 9
    assert expired > today


def test_weight_decreases_with_remaining_days() -> None:
    """Чем меньше остаточный срок, тем больше вес — функция невозрастающая."""
    horizon = 10
    weights = [UrgencyCalculator.weight(days, horizon) for days in range(0, 15)]

    assert weights == sorted(weights, reverse=True)


def test_calculator_is_stateless() -> None:
    """Горизонт передаётся аргументом и нигде не запоминается.

    Вид весовой функции по условию курсовой должен меняться независимо
    от алгоритма, поэтому состояния у калькулятора нет.
    """
    assert UrgencyCalculator().__dict__ == {}
    assert UrgencyCalculator.weight(2, 7) == 5
    assert UrgencyCalculator.weight(2, 3) == 1
    assert UrgencyCalculator.weight(2, 7) == 5
