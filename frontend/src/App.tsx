/**
 * Корневой компонент: состояние приложения и переходы между экранами.
 *
 * Состояние держится в React без внешних библиотек — экранов четыре,
 * данные плоские. Роутинг тоже минимальный: текущий экран в состоянии,
 * без адресной строки. Mini app открывается всегда с одного места,
 * ссылки внутрь него не нужны.
 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from './api'
import type { Ingredient, Product, ProductCreate, Recipe, Settings, StoragePlace } from './api'
import { NewProductPage } from './pages/NewProductPage'
import { ProductsPage } from './pages/ProductsPage'
import { RecommendationsPage } from './pages/RecommendationsPage'
import { SettingsPage } from './pages/SettingsPage'

type ScreenName = 'products' | 'new-product' | 'recommendations' | 'settings'

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Не удалось выполнить запрос'
}

export function App() {
  const [screen, setScreen] = useState<ScreenName>('products')

  const [products, setProducts] = useState<Product[]>([])
  const [places, setPlaces] = useState<StoragePlace[]>([])
  const [ingredients, setIngredients] = useState<Ingredient[]>([])
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [settings, setSettings] = useState<Settings | null>(null)

  const [loading, setLoading] = useState(true)
  const [recipesLoading, setRecipesLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [writingOff, setWritingOff] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadProducts = useCallback(async () => {
    const list = await api.listProducts()
    setProducts(list)
  }, [])

  // Справочники и перечень загружаются один раз при открытии: они нужны
  // сразу нескольким экранам, а объём небольшой
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [productList, placeList, ingredientList, currentSettings] = await Promise.all([
          api.listProducts(),
          api.listStoragePlaces(),
          api.listIngredients(),
          api.getSettings(),
        ])
        if (cancelled) return
        setProducts(productList)
        setPlaces(placeList)
        setIngredients(ingredientList)
        setSettings(currentSettings)
        setError(null)
      } catch (cause) {
        if (!cancelled) setError(describe(cause))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const loadRecommendations = useCallback(async () => {
    setRecipesLoading(true)
    setError(null)
    try {
      setRecipes(await api.getRecommendations())
    } catch (cause) {
      setError(describe(cause))
    } finally {
      setRecipesLoading(false)
    }
  }, [])

  function openRecommendations() {
    setScreen('recommendations')
    void loadRecommendations()
  }

  async function saveProduct(product: ProductCreate) {
    setSaving(true)
    setError(null)
    try {
      await api.createProduct(product)
      await loadProducts()
      setScreen('products')
    } catch (cause) {
      setError(describe(cause))
    } finally {
      setSaving(false)
    }
  }

  async function saveSettings(changes: Settings) {
    setSaving(true)
    setError(null)
    try {
      setSettings(await api.updateSettings(changes))
      // Горизонт влияет на цветовую индикацию, поэтому перечень перечитывается
      await loadProducts()
      setScreen('products')
    } catch (cause) {
      setError(describe(cause))
    } finally {
      setSaving(false)
    }
  }

  /**
   * Отмечает использованными продукты, покрытые выбранным рецептом.
   * Их состав пришёл с сервера — это результат работы жадного алгоритма.
   */
  async function writeOff(recipe: Recipe) {
    setWritingOff(recipe.title)
    setError(null)
    try {
      for (const productId of recipe.covered_product_ids) {
        await api.setProductStatus(productId, 'used')
      }
      await loadProducts()
      await loadRecommendations()
    } catch (cause) {
      setError(describe(cause))
    } finally {
      setWritingOff(null)
    }
  }

  if (screen === 'new-product') {
    return (
      <NewProductPage
        ingredients={ingredients}
        places={places}
        saving={saving}
        error={error}
        onSave={(product) => void saveProduct(product)}
        onBack={() => {
          setError(null)
          setScreen('products')
        }}
      />
    )
  }

  if (screen === 'recommendations') {
    return (
      <RecommendationsPage
        recipes={recipes}
        products={products}
        loading={recipesLoading}
        error={error}
        writingOff={writingOff}
        onRefresh={() => void loadRecommendations()}
        onWriteOff={(recipe) => void writeOff(recipe)}
        onOpenProducts={() => setScreen('products')}
        onBack={() => setScreen('products')}
      />
    )
  }

  if (screen === 'settings' && settings) {
    return (
      <SettingsPage
        settings={settings}
        saving={saving}
        error={error}
        onSave={(changes) => void saveSettings(changes)}
        onBack={() => {
          setError(null)
          setScreen('products')
        }}
      />
    )
  }

  return (
    <ProductsPage
      products={products}
      places={places}
      ingredients={ingredients}
      loading={loading}
      error={error}
      onAdd={() => setScreen('new-product')}
      onOpenRecommendations={openRecommendations}
      onOpenSettings={() => settings && setScreen('settings')}
    />
  )
}
