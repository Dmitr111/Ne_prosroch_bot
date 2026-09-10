"""Модели SQLAlchemy (13 сущностей).

Описывает declarative-базу и таблицы предметной области: пользователи,
продукты, категории, места хранения, единицы измерения, рецепты и их
ингредиенты, рекомендации, настройки и уведомления.

Ключи следуют решению из курсовой: справочники и пользователь опираются
на естественные ключи, редактируемые пользователем сущности получают
суррогатный ``id``, а естественный ключ остаётся UNIQUE-ограничением.

Правило удаления: пользовательские данные удаляются каскадом вслед за
владельцем, ссылки на справочники защищены RESTRICT — справочник,
на который ссылаются, удалить нельзя.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


# Время ежедневного напоминания, если пользователь его не менял.
# На эту же константу опирается отбор получателей в SettingsRepository:
# у пользователя может ещё не быть строки в user_settings
DEFAULT_NOTIFY_TIME = time(9, 0)


class ProductStatusCode:
    """Коды из справочника product_statuses.

    Вынесены в константы: на них опираются значение по умолчанию колонки
    products.status_code, наполнение справочника и выборка активных
    продуктов в репозитории.
    """

    IN_STOCK = "in_stock"
    USED = "used"
    # Реальные пищевые потери: продукт испортился. Учитывается
    # в статистике третьей главы
    WRITTEN_OFF = "written_off"
    # Ошибочно внесённая позиция, убранная из перечня. Потерями
    # не является и в статистику потерь не входит
    REMOVED = "removed"


# ---------------------------------------------------------------------------
# Пользователь и его настройки
# ---------------------------------------------------------------------------


class User(Base):
    """Пользователь Telegram.

    Естественный ключ — ``telegram_id``: отдельной регистрации нет,
    запись заводится при первом обращении к mini app.
    """

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    username: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    storage_places: Mapped[list["StoragePlace"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    recommendation_sessions: Mapped[list["RecommendationSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserSettings(Base):
    """Параметры напоминаний и подбора.

    Связь с пользователем один к одному, поэтому ``telegram_id`` служит
    одновременно первичным и внешним ключом.
    """

    __tablename__ = "user_settings"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )
    # Время ежедневной рассылки напоминаний, задаётся пользователем.
    # Планировщик обходит пользователей ежечасно и берёт тех, у кого
    # совпал час; DAILY_CHECK_TIME к напоминаниям отношения не имеет
    notify_time: Mapped[time] = mapped_column(
        Time, nullable=False, server_default=text(f"'{DEFAULT_NOTIFY_TIME:%H:%M}'")
    )
    # За сколько дней до истечения срока продукт считается срочным
    threshold_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )
    # Горизонт планирования T из формулы веса срочности
    horizon_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("7")
    )
    # Ограничение k на размер набора рецептов
    recommend_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )

    user: Mapped["User"] = relationship(back_populates="settings")


class StoragePlace(Base):
    """Место хранения продуктов («холодильник», «морозилка»).

    Наименование правится пользователем, поэтому ключ суррогатный,
    а естественная уникальность вынесена в ограничение.
    """

    __tablename__ = "storage_places"
    # Отдельный индекс по telegram_id не нужен: колонка ведущая в UNIQUE
    __table_args__ = (
        UniqueConstraint("telegram_id", "name", name="uq_storage_places_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship(back_populates="storage_places")
    products: Mapped[list["Product"]] = relationship(back_populates="storage_place")


# ---------------------------------------------------------------------------
# Справочники: наполняются миграциями и seed.py, пользователем не правятся
# ---------------------------------------------------------------------------


class Category(Base):
    """Категория ингредиентов («молочные продукты», «крупы»)."""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)

    ingredients: Mapped[list["Ingredient"]] = relationship(back_populates="category")


class Ingredient(Base):
    """Типовой ингредиент («молоко») — единица состава рецепта.

    Отличается от ``products.name``, где хранится пользовательское
    наименование конкретного экземпляра запасов.
    """

    __tablename__ = "ingredients"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    category_name: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("categories.name", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped["Category"] = relationship(back_populates="ingredients")
    products: Mapped[list["Product"]] = relationship(back_populates="ingredient")
    recipe_links: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="ingredient"
    )


class ProductStatus(Base):
    """Статус позиции запасов: в наличии / использован / списан.

    Продукты физически не удаляются, вместо этого меняется ``status_code``.
    """

    __tablename__ = "product_statuses"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="status")


class Recipe(Base):
    """Рецепт; естественный ключ — наименование."""

    __tablename__ = "recipes"

    title: Mapped[str] = mapped_column(String(255), primary_key=True)
    description: Mapped[str | None] = mapped_column(Text)
    cooking_time_min: Mapped[int | None] = mapped_column(Integer)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", passive_deletes=True
    )
    recommendation_links: Mapped[list["RecommendationItem"]] = relationship(
        back_populates="recipe"
    )


class RecipeIngredient(Base):
    """Состав рецепта: связка «рецепт — ингредиент» с количеством.

    Первичный ключ составной, из двух внешних ключей.
    """

    __tablename__ = "recipe_ingredients"

    recipe_title: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("recipes.title", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    ingredient_name: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("ingredients.name", ondelete="RESTRICT", onupdate="CASCADE"),
        primary_key=True,
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    unit: Mapped[str | None] = mapped_column(String(16))

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="recipe_links")


# ---------------------------------------------------------------------------
# Запасы пользователя
# ---------------------------------------------------------------------------


class Product(Base):
    """Позиция домашних запасов.

    Уникальна по тройке ``(telegram_id, name, expiry_date)``: одинаковые
    продукты с совпадающим сроком объединяются в одну запись и различаются
    значением ``quantity``.
    """

    __tablename__ = "products"
    # Отдельный индекс по telegram_id не нужен: колонка ведущая в UNIQUE
    __table_args__ = (
        UniqueConstraint(
            "telegram_id", "name", "expiry_date", name="uq_products_owner_name_expiry"
        ),
        CheckConstraint("quantity > 0", name="ck_products_quantity_positive"),
        # Дата изготовления необязательна, но если указана — не позже срока годности
        CheckConstraint(
            "manufacture_date IS NULL OR expiry_date >= manufacture_date",
            name="ck_products_expiry_after_manufacture",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    manufacture_date: Mapped[date | None] = mapped_column(Date)
    # Связь с типовым ингредиентом обязательна: при α = 1 рецепт считается
    # применимым, только если каждый его ингредиент есть в запасах, поэтому
    # продукт без привязки к справочнику в подборе бесполезен
    ingredient_name: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("ingredients.name", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_place_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("storage_places.id", ondelete="SET NULL")
    )
    status_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("product_statuses.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        server_default=text(f"'{ProductStatusCode.IN_STOCK}'"),
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, server_default=text("1")
    )
    unit: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'шт'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="products")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="products")
    storage_place: Mapped["StoragePlace | None"] = relationship(
        back_populates="products"
    )
    status: Mapped["ProductStatus"] = relationship(back_populates="products")
    notification_links: Mapped[list["NotificationItem"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )


# ---------------------------------------------------------------------------
# Напоминания
# ---------------------------------------------------------------------------


class Notification(Base):
    """Отправленное напоминание.

    Одно напоминание может касаться нескольких продуктов, поэтому состав
    вынесен в ``notification_items``.
    """

    __tablename__ = "notifications"
    # Отдельный индекс по telegram_id не нужен: колонка ведущая в UNIQUE
    __table_args__ = (
        UniqueConstraint("telegram_id", "sent_at", name="uq_notifications_owner_sent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Вид напоминания: первичное о приближении срока или повторное
    type: Mapped[str] = mapped_column(String(32), nullable=False)

    user: Mapped["User"] = relationship(back_populates="notifications")
    items: Mapped[list["NotificationItem"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan", passive_deletes=True
    )


class NotificationItem(Base):
    """Продукт, упомянутый в напоминании. Первичный ключ составной."""

    __tablename__ = "notification_items"

    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )

    notification: Mapped["Notification"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="notification_links")


# ---------------------------------------------------------------------------
# Рекомендации: фиксируют условия запуска подбора для эксперимента
# ---------------------------------------------------------------------------


class RecommendationSession(Base):
    """Запуск подбора рецептов с зафиксированными параметрами T и k."""

    __tablename__ = "recommendation_sessions"
    # Отдельный индекс по telegram_id не нужен: колонка ведущая в UNIQUE
    __table_args__ = (
        UniqueConstraint(
            "telegram_id", "created_at", name="uq_recommendation_sessions_owner_created"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Источник запуска: напоминание или запрос пользователя
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    # Действовавшие на момент запуска значения горизонта T и ограничения k
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    k: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="recommendation_sessions")
    items: Mapped[list["RecommendationItem"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RecommendationItem.position",
    )


class RecommendationItem(Base):
    """Рецепт, отобранный жадным алгоритмом. Первичный ключ составной."""

    __tablename__ = "recommendation_items"

    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recommendation_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    recipe_title: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("recipes.title", ondelete="RESTRICT", onupdate="CASCADE"),
        primary_key=True,
    )
    # Порядковый номер шага жадного алгоритма, с единицы
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Прирост полезности V(S) на этом шаге
    covered_weight: Mapped[int] = mapped_column(Integer, nullable=False)

    session: Mapped["RecommendationSession"] = relationship(back_populates="items")
    recipe: Mapped["Recipe"] = relationship(back_populates="recommendation_links")
