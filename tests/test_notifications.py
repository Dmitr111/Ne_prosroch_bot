"""Тесты текста напоминаний и правил повторной отправки.

Проверяется чистая логика: формирование сообщения и суточная пауза.
Telegram и БД не задействованы.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from backend.bot.notifications import NO_RECIPES_TEXT, format_expiry_message
from backend.repositories.notifications import NotificationType
from backend.scheduler.jobs import notification_type, products_to_notify

TODAY = date(2026, 3, 10)
NOW = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


@dataclass
class FakeProduct:
    id: int
    name: str
    expiry_date: date


@dataclass
class FakeRecipe:
    title: str
    cooking_time_min: int | None = None


def product(product_id: int, name: str, days_left: int) -> FakeProduct:
    return FakeProduct(
        id=product_id, name=name, expiry_date=TODAY + timedelta(days=days_left)
    )


# ---------------------------------------------------------------------------
# Текст напоминания
# ---------------------------------------------------------------------------


def test_message_marks_today_red_and_upcoming_yellow() -> None:
    message = format_expiry_message(
        [product(1, "Молоко", 0), product(2, "Творог", 2)],
        [FakeRecipe("Сырники", 25)],
        TODAY,
    )

    assert "🔴 Молоко — сегодня" in message
    assert "🟡 Творог — через 2 дня" in message
    assert "• Сырники — 25 мин" in message


def test_message_without_recipes_still_informs() -> None:
    """Пустой набор рецептов не отменяет напоминание."""
    message = format_expiry_message([product(1, "Молоко", 1)], [], TODAY)

    assert "Молоко" in message
    assert NO_RECIPES_TEXT in message


def test_recipe_without_cooking_time() -> None:
    message = format_expiry_message(
        [product(1, "Молоко", 1)], [FakeRecipe("Коктейль", None)], TODAY
    )

    assert "• Коктейль" in message
    assert "мин" not in message


def test_day_forms() -> None:
    """Окончания числительных: день, дня, дней."""
    products = [
        product(1, "Сегодня", 0),
        product(2, "Завтра", 1),
        product(3, "Двое", 2),
        product(4, "Пятеро", 5),
        product(5, "Одиннадцать", 11),
        product(6, "Двадцать один", 21),
    ]

    message = format_expiry_message(products, [], TODAY)

    assert "Сегодня — сегодня" in message
    assert "Завтра — завтра" in message
    assert "Двое — через 2 дня" in message
    assert "Пятеро — через 5 дней" in message
    assert "Одиннадцать — через 11 дней" in message
    assert "Двадцать один — через 21 день" in message


def test_expired_product_is_marked_red() -> None:
    """Просроченное в рассылку обычно не попадает, но помечается красным."""
    message = format_expiry_message([product(1, "Кефир", -1)], [], TODAY)

    assert message.startswith("Скоро истекает срок годности:")
    assert "🔴 Кефир" in message


# ---------------------------------------------------------------------------
# Суточная пауза
# ---------------------------------------------------------------------------


def test_product_notified_today_is_skipped() -> None:
    """О продукте, про который сообщали час назад, повторно не пишем."""
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(hours=1)}

    assert products_to_notify([milk], last_notified, NOW) == []


def test_product_notified_yesterday_is_repeated() -> None:
    """Циклический таймер R/P1D: через сутки напоминание повторяется."""
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(days=1, minutes=1)}

    assert products_to_notify([milk], last_notified, NOW) == [milk]


def test_period_tolerates_hourly_run_drift() -> None:
    """Почти сутки — уже повод напомнить снова.

    Задача стартует в начале часа, а отметка в журнале ставится на
    секунды позже. Назавтра в тот же час проходит 23:59:5x, и при паузе
    ровно в сутки напоминание срывалось бы каждый день.
    """
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(hours=23, minutes=59, seconds=57)}

    assert products_to_notify([milk], last_notified, NOW) == [milk]


def test_product_notified_hours_ago_is_still_skipped() -> None:
    """Внутри суток повторов нет: 12 часов — рано."""
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(hours=12)}

    assert products_to_notify([milk], last_notified, NOW) == []


def test_product_never_notified_is_selected() -> None:
    milk = product(1, "Молоко", 1)

    assert products_to_notify([milk], {}, NOW) == [milk]


def test_only_fresh_products_are_selected() -> None:
    """Из смешанного перечня остаются только те, о ком пора напомнить."""
    milk = product(1, "Молоко", 1)
    curd = product(2, "Творог", 2)
    bread = product(3, "Хлеб", 0)
    last_notified = {1: NOW - timedelta(hours=2), 2: NOW - timedelta(days=3)}

    selected = products_to_notify([milk, curd, bread], last_notified, NOW)

    assert [item.name for item in selected] == ["Творог", "Хлеб"]


# ---------------------------------------------------------------------------
# Вид напоминания
# ---------------------------------------------------------------------------


def test_type_is_expiry_for_new_product() -> None:
    assert notification_type([product(1, "Молоко", 1)], {}) == NotificationType.EXPIRY


def test_type_is_repeat_when_all_products_known() -> None:
    milk = product(1, "Молоко", 1)
    last_notified = {1: NOW - timedelta(days=2)}

    assert notification_type([milk], last_notified) == NotificationType.REPEAT


def test_type_is_expiry_when_at_least_one_product_is_new() -> None:
    """Появился новый продукт — напоминание считается первичным."""
    milk = product(1, "Молоко", 1)
    bread = product(2, "Хлеб", 0)
    last_notified = {1: NOW - timedelta(days=2)}

    assert notification_type([milk, bread], last_notified) == NotificationType.EXPIRY
