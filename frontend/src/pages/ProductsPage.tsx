/**
 * Экран «Мои продукты» (рисунок 2.4).
 *
 * Список сгруппирован по местам хранения, срочность показана цветом
 * из поля `urgency` ответа API — на клиенте она не пересчитывается,
 * иначе границы подсветки разошлись бы с весовой функцией подбора.
 */

import { useMemo, useState } from 'react'
import type { Ingredient, Product, StoragePlace } from '../api'
import { MainButton } from '../components/MainButton'
import { Screen } from '../components/Screen'
import { Tabs } from '../components/Tabs'
import { formatDaysLeft, formatQuantity } from '../utils/format'

const WITHOUT_PLACE = 'Без места хранения'

interface ProductsPageProps {
  products: Product[]
  places: StoragePlace[]
  ingredients: Ingredient[]
  loading: boolean
  error: string | null
  onAdd: () => void
  onEdit: (product: Product) => void
  onOpenRecommendations: () => void
  onOpenSettings: () => void
  /** На корневом экране возвращаться некуда, стрелка не показывается */
  onBack?: () => void
}

export function ProductsPage({
  products,
  places,
  ingredients,
  loading,
  error,
  onAdd,
  onEdit,
  onOpenRecommendations,
  onOpenSettings,
  onBack,
}: ProductsPageProps) {
  const [query, setQuery] = useState('')
  const [searchVisible, setSearchVisible] = useState(false)

  // Категория продукта отдельно не хранится, а выводится из ингредиента,
  // поэтому подпись карточки собирается по справочнику
  const categoryOf = useMemo(() => {
    const byIngredient = new Map(ingredients.map((item) => [item.name, item.category_name]))
    return (product: Product) => byIngredient.get(product.ingredient_name) ?? ''
  }, [ingredients])

  const groups = useMemo(() => {
    const placeNames = new Map(places.map((place) => [place.id, place.name]))
    const needle = query.trim().toLowerCase()
    const visible = needle
      ? products.filter(
          (product) =>
            product.name.toLowerCase().includes(needle) ||
            product.ingredient_name.toLowerCase().includes(needle),
        )
      : products

    const byPlace = new Map<string, Product[]>()
    for (const product of visible) {
      const place =
        product.storage_place_id === null
          ? WITHOUT_PLACE
          : (placeNames.get(product.storage_place_id) ?? WITHOUT_PLACE)
      const group = byPlace.get(place)
      if (group) group.push(product)
      else byPlace.set(place, [product])
    }
    // Места хранения — в порядке самого срочного продукта, позиции без места — в конце
    return [...byPlace.entries()].sort(
      ([a], [b]) => Number(a === WITHOUT_PLACE) - Number(b === WITHOUT_PLACE),
    )
  }, [products, places, query])

  return (
    <Screen
      title="Мои продукты"
      onBack={onBack}
      actions={
        <>
          <button
            className="icon-button"
            aria-label="Поиск"
            onClick={() => {
              setSearchVisible((visible) => !visible)
              setQuery('')
            }}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <circle
                cx="11"
                cy="11"
                r="6.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
              />
              <path
                d="M16 16 L21 21"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <button className="icon-button" aria-label="Настройки" onClick={onOpenSettings}>
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <circle
                cx="12"
                cy="12"
                r="3.2"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
              />
              <path
                d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </>
      }
      footer={<MainButton text="Добавить продукт" onClick={onAdd} />}
    >
      <Tabs active="products" onChange={(tab) => tab === 'recommendations' && onOpenRecommendations()} />

      {searchVisible && (
        <input
          className="control search"
          type="search"
          placeholder="Поиск по названию"
          value={query}
          autoFocus
          onChange={(event) => setQuery(event.target.value)}
        />
      )}

      {error && <p className="notice notice--error">{error}</p>}
      {loading && <p className="notice">Загружаем перечень…</p>}

      {!loading && !error && groups.length === 0 && (
        <p className="notice">
          {query ? 'Ничего не нашлось.' : 'Пока пусто. Добавьте первый продукт.'}
        </p>
      )}

      {groups.map(([place, items]) => (
        <section key={place} className="group">
          <h2 className="group__title">{place.toUpperCase()}</h2>
          <ul className="card-list">
            {items.map((product) => (
              <li key={product.id}>
                {/* Карточка — кнопка: касание открывает редактирование */}
                <button className="card product" onClick={() => onEdit(product)}>
                  <span className={`dot dot--${product.urgency}`} aria-hidden="true" />
                  <span className="product__text">
                    <span className="product__name">{product.name}</span>
                    <span className="product__meta">
                      {formatQuantity(product.quantity)} {product.unit}
                      {categoryOf(product) && ` · ${categoryOf(product)}`}
                    </span>
                  </span>
                  <span className={`product__days product__days--${product.urgency}`}>
                    {formatDaysLeft(product.days_left)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </Screen>
  )
}
