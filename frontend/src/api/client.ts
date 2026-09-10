/**
 * Базовый клиент REST API.
 *
 * Подпись initData уходит в заголовке `Authorization: tma <initData>`
 * с каждым запросом: сервер проверяет её и по ней же определяет
 * пользователя — отдельного идентификатора в запросах нет и быть
 * не должно, иначе его можно было бы подменить.
 */

import { getInitData } from '../telegram'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

/** Ошибка запроса с кодом ответа и текстом из поля detail. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function describe(status: number, body: unknown): string {
  if (status === 401) return 'Не удалось подтвердить подпись Telegram'
  if (status === 409) return 'Такой продукт с этим сроком годности уже добавлен'

  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    // Ошибка валидации FastAPI приходит списком объектов
    if (Array.isArray(detail)) {
      const first = detail[0]
      if (first && typeof first === 'object' && 'msg' in first) {
        return String((first as { msg: unknown }).msg)
      }
    }
  }
  return `Ошибка запроса (${status})`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Authorization', `tma ${getInitData()}`)
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Сервер недоступен, проверьте соединение')
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const body: unknown = text ? JSON.parse(text) : null

  if (!response.ok) throw new ApiError(response.status, describe(response.status, body))
  return body as T
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: 'DELETE' }),
}
