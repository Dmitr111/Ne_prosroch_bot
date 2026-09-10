/** Типы ответов REST API, повторяют схемы Pydantic из backend/api/schemas.py. */

/** Цветовая индикация остаточного срока. */
export type Urgency = 'green' | 'yellow' | 'red'

/** Статусы, которые проставляются отметкой. Removed ставится через DELETE. */
export type StatusCode = 'in_stock' | 'used' | 'written_off'

export interface Product {
  id: number
  name: string
  expiry_date: string
  manufacture_date: string | null
  ingredient_name: string
  storage_place_id: number | null
  status_code: string
  quantity: number
  unit: string
  /** Остаточный срок в днях, отрицательный — просрочено */
  days_left: number
  urgency: Urgency
}

export interface ProductCreate {
  name: string
  expiry_date: string
  manufacture_date?: string | null
  ingredient_name: string
  storage_place_id?: number | null
  quantity: number
  unit: string
}

export interface StoragePlace {
  id: number
  name: string
}

export interface Category {
  name: string
}

export interface Ingredient {
  name: string
  category_name: string
}

export interface Recipe {
  title: string
  description: string | null
  cooking_time_min: number | null
  ingredients: string[]
  /**
   * Истекающие продукты, покрытые этим рецептом. Считает жадный алгоритм:
   * продукт засчитывается рецепту, который взял его первым, поэтому наборы
   * разных рецептов не пересекаются. Пересчитывать это на клиенте нельзя —
   * здесь нет ни весов срочности, ни порядка отбора.
   */
  covered_product_ids: number[]
  /** Ингредиенты покрытых продуктов — их состав подсвечивается */
  covered_ingredients: string[]
  /** Прирост полезности, сумма весов покрытых продуктов */
  covered_weight: number
}

export interface Settings {
  /** Время в формате HH:MM:SS */
  notify_time: string
  threshold_days: number
  horizon_days: number
  recommend_limit: number
}

export type SettingsUpdate = Partial<Settings>
