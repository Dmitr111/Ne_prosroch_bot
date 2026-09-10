/** Методы REST API, по одному на эндпоинт из курсовой. */

import { http } from './client'
import type {
  Ingredient,
  Product,
  ProductCreate,
  Recipe,
  Settings,
  SettingsUpdate,
  StatusCode,
  StoragePlace,
} from './types'

export const api = {
  /** Перечень продуктов; по умолчанию только то, что в наличии. */
  listProducts: (status?: string) =>
    http.get<Product[]>(status ? `/products?status=${status}` : '/products'),

  createProduct: (product: ProductCreate) => http.post<Product>('/products', product),

  updateProduct: (id: number, changes: Partial<ProductCreate>) =>
    http.patch<Product>(`/products/${id}`, changes),

  /** Удаление из перечня: сервер проставляет статус «удалён». */
  deleteProduct: (id: number) => http.delete(`/products/${id}`),

  /** Отметка «использован» или «списан». */
  setProductStatus: (id: number, statusCode: StatusCode) =>
    http.post<Product>(`/products/${id}/status`, { status_code: statusCode }),

  listStoragePlaces: () => http.get<StoragePlace[]>('/storage-places'),

  listIngredients: () => http.get<Ingredient[]>('/ingredients'),

  getRecommendations: () => http.get<Recipe[]>('/recommendations'),

  getSettings: () => http.get<Settings>('/settings'),

  updateSettings: (changes: SettingsUpdate) => http.patch<Settings>('/settings', changes),
}

export { ApiError } from './client'
export type * from './types'
