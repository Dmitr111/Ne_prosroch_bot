/**
 * Корневой компонент: состояние приложения и переходы между экранами.
 *
 * Состояние держится в React без внешних библиотек — экранов пять,
 * данные плоские. Роутинг тоже минимальный: текущий экран в состоянии,
 * без адресной строки. Mini app открывается всегда с одного места,
 * ссылки внутрь него не нужны.
 *
 * Все переходы идут через navigate(): он же сбрасывает ошибку. Раньше
 * ошибка одного экрана оставалась висеть на следующем — например, сбой
 * подбора показывался на вкладке «Продукты».
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from './api'
import type {
  Ingredient,
  Product,
  ProductCreate,
  Recipe,
  Settings,
  StatusCode,
  StoragePlace,
} from './api'
import { ProductFormPage } from './pages/ProductFormPage'
import { ProductsPage } from './pages/ProductsPage'
import { RecommendationsPage } from './pages/RecommendationsPage'
import { SettingsPage } from './pages/SettingsPage'

type Screen =
  | { name: 'products' }
  | { name: 'new-product' }
  // Снимок продукта, а не id: после отметки «использован» позиция уходит
  // из перечня в наличии, и поиск по id на мгновение не находил бы её
  | { name: 'edit-product'; product: Product }
  | { name: 'recommendations' }
  | { name: 'settings' }

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Не удалось выполнить запрос'
}

export function App() {
  const [screen, setScreen] = useState<Screen>({ name: 'products' })

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

  const navigate = useCallback((next: Screen) => {
    setError(null)
    setScreen(next)
  }, [])

  // Текущий экран для асинхронных обработчиков: ответ подбора может прийти,
  // когда пользователь уже ушёл на другую вкладку
  const screenRef = useRef(screen)
  useEffect(() => {
    screenRef.current = screen
  }, [screen])

  const loadProducts = useCallback(async () => {
    setProducts(await api.listProducts())
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
      // Ошибку подбора показываем только на экране подбора
      if (screenRef.current.name === 'recommendations') setError(describe(cause))
    } finally {
      setRecipesLoading(false)
    }
  }, [])

  function openRecommendations() {
    navigate({ name: 'recommendations' })
    void loadRecommendations()
  }

  /** Общая обёртка изменений: индикатор, ошибка, перечитывание перечня. */
  async function mutate(action: () => Promise<unknown>) {
    setSaving(true)
    setError(null)
    try {
      await action()
      await loadProducts()
      navigate({ name: 'products' })
    } catch (cause) {
      setError(describe(cause))
    } finally {
      setSaving(false)
    }
  }

  function createProduct(product: ProductCreate) {
    void mutate(() => api.createProduct(product))
  }

  function updateProduct(id: number, product: ProductCreate) {
    void mutate(() => api.updateProduct(id, product))
  }

  function setProductStatus(id: number, status: StatusCode) {
    void mutate(() => api.setProductStatus(id, status))
  }

  function removeProduct(id: number) {
    void mutate(() => api.deleteProduct(id))
  }

  async function saveSettings(changes: Settings) {
    setSaving(true)
    setError(null)
    try {
      setSettings(await api.updateSettings(changes))
      // Горизонт влияет на цветовую индикацию, поэтому перечень перечитывается
      await loadProducts()
      navigate({ name: 'products' })
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
    } catch (cause) {
      setError(describe(cause))
    } finally {
      // Перечитываем и после сбоя: часть продуктов могла уже списаться,
      // и экран не должен показывать устаревшее состояние
      try {
        await loadProducts()
      } catch {
        // Ошибка уже показана
      }
      await loadRecommendations()
      setWritingOff(null)
    }
  }

  const back = () => navigate({ name: 'products' })

  switch (screen.name) {
    case 'new-product':
      return (
        <ProductFormPage
          ingredients={ingredients}
          places={places}
          saving={saving}
          error={error}
          onSave={createProduct}
          onBack={back}
        />
      )

    case 'edit-product': {
      const { product } = screen
      return (
        <ProductFormPage
          // key: при переходе к другому продукту форма заполняется заново
          key={product.id}
          product={product}
          ingredients={ingredients}
          places={places}
          saving={saving}
          error={error}
          onSave={(values) => updateProduct(product.id, values)}
          onSetStatus={(status) => setProductStatus(product.id, status)}
          onRemove={() => removeProduct(product.id)}
          onBack={back}
        />
      )
    }

    case 'recommendations':
      return (
        <RecommendationsPage
          recipes={recipes}
          products={products}
          loading={recipesLoading}
          error={error}
          writingOff={writingOff}
          onRefresh={() => void loadRecommendations()}
          onWriteOff={(recipe) => void writeOff(recipe)}
          onOpenProducts={back}
          onBack={back}
        />
      )

    case 'settings':
      if (!settings) return null
      return (
        <SettingsPage
          settings={settings}
          saving={saving}
          error={error}
          onSave={(changes) => void saveSettings(changes)}
          onBack={back}
        />
      )

    case 'products':
      return (
        <ProductsPage
          products={products}
          places={places}
          ingredients={ingredients}
          loading={loading}
          error={error}
          onAdd={() => navigate({ name: 'new-product' })}
          onEdit={(product) => navigate({ name: 'edit-product', product })}
          onOpenRecommendations={openRecommendations}
          onOpenSettings={() => settings && navigate({ name: 'settings' })}
        />
      )
  }
}
