/**
 * Экран «Рекомендации» (рисунок 2.5, левая часть).
 *
 * Покрытие рецепта приходит с сервера: какие продукты он спасает
 * (`covered_product_ids`), какие ингредиенты выделять
 * (`covered_ingredients`) и сколько их. Клиент это не пересчитывает —
 * пересечение считает жадный алгоритм, и только он знает веса срочности
 * и порядок отбора. Без порядка один продукт попал бы сразу в несколько
 * рецептов и списался бы дважды.
 */

import { useMemo } from 'react'
import type { Product, Recipe } from '../api'
import { MainButton } from '../components/MainButton'
import { Screen } from '../components/Screen'
import { Tabs } from '../components/Tabs'
import { formatExpiryHint } from '../utils/format'

interface RecommendationsPageProps {
  recipes: Recipe[]
  products: Product[]
  loading: boolean
  error: string | null
  writingOff: string | null
  onRefresh: () => void
  onWriteOff: (recipe: Recipe) => void
  onOpenProducts: () => void
  onBack: () => void
}

export function RecommendationsPage({
  recipes,
  products,
  loading,
  error,
  writingOff,
  onRefresh,
  onWriteOff,
  onOpenProducts,
  onBack,
}: RecommendationsPageProps) {
  // Перечень истекающего — это фильтр собственных запасов, а не пересечение
  // с рецептами, поэтому он остаётся на клиенте
  const expiring = useMemo(
    () => products.filter((product) => product.urgency !== 'green'),
    [products],
  )

  return (
    <Screen
      title="Рекомендации"
      onBack={onBack}
      footer={<MainButton text="Обновить подборку" onClick={onRefresh} progress={loading} />}
    >
      <Tabs
        active="recommendations"
        onChange={(tab) => tab === 'products' && onOpenProducts()}
      />

      {error && <p className="notice notice--error">{error}</p>}

      {expiring.length > 0 && (
        <div className="expiring">
          <p className="expiring__title">Скоро истекают:</p>
          <p className="expiring__list">
            {expiring
              .map((product) =>
                product.urgency === 'red'
                  ? `${product.ingredient_name} (${formatExpiryHint(product.days_left)})`
                  : product.ingredient_name,
              )
              .join(', ')}
          </p>
        </div>
      )}

      {loading && <p className="notice">Подбираем рецепты…</p>}

      {!loading && !error && recipes.length === 0 && (
        <p className="notice">
          Подходящих рецептов не нашлось: для рецепта нужны все его ингредиенты.
        </p>
      )}

      <ul className="card-list">
        {recipes.map((recipe) => {
          const covered = new Set(recipe.covered_ingredients)
          return (
            <li key={recipe.title} className="card recipe">
              <h3 className="recipe__title">{recipe.title}</h3>
              <p className="recipe__ingredients">
                {recipe.ingredients.map((name, index) => (
                  <span key={name}>
                    {index > 0 && ', '}
                    <span className={covered.has(name) ? 'recipe__ingredient--expiring' : ''}>
                      {name}
                    </span>
                  </span>
                ))}
              </p>
              {recipe.cooking_time_min !== null && (
                <p className="recipe__time">{recipe.cooking_time_min} мин</p>
              )}
              <div className="recipe__actions">
                <span className="badge">
                  истекающих: {recipe.covered_product_ids.length}
                </span>
                <button
                  className="button"
                  disabled={
                    recipe.covered_product_ids.length === 0 || writingOff === recipe.title
                  }
                  onClick={() => onWriteOff(recipe)}
                >
                  {writingOff === recipe.title ? 'Списываем…' : 'Списать продукты'}
                </button>
              </div>
            </li>
          )
        })}
      </ul>

      {recipes.length > 0 && (
        <p className="footnote">Подобрано по приоритету сроков годности</p>
      )}
    </Screen>
  )
}
