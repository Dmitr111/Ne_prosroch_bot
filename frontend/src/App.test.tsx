/**
 * Кнопка действия экрана.
 *
 * Дефект уже возвращался: подпись одного экрана оставалась на другом
 * («Добавить продукт» в настройках, «Обновить подборку» на вкладке
 * «Продукты»), а MainButton клиента и запасная кнопка рисовались вместе.
 * Тест проходит по всем экранам через настоящую навигацию App и на каждом
 * проверяет, что кнопка ровно одна и подпись у неё своя. Отдельно следит,
 * что к MainButton клиента никто не обращается.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api } from './api'
import type { Ingredient, Product, Recipe, Settings, StoragePlace } from './api'

vi.mock('./api', () => {
  class ApiError extends Error {
    status = 0
  }
  return {
    ApiError,
    api: {
      listProducts: vi.fn(),
      createProduct: vi.fn(),
      updateProduct: vi.fn(),
      deleteProduct: vi.fn(),
      setProductStatus: vi.fn(),
      listStoragePlaces: vi.fn(),
      listIngredients: vi.fn(),
      getRecommendations: vi.fn(),
      getSettings: vi.fn(),
      updateSettings: vi.fn(),
    },
  }
})

const PRODUCTS: Product[] = [
  {
    id: 1,
    name: 'Молоко 3,2 %',
    expiry_date: '2026-09-13',
    manufacture_date: null,
    ingredient_name: 'молоко',
    storage_place_id: 1,
    status_code: 'in_stock',
    quantity: 1,
    unit: 'л',
    days_left: 2,
    urgency: 'yellow',
  },
]
const PLACES: StoragePlace[] = [{ id: 1, name: 'Холодильник' }]
const INGREDIENTS: Ingredient[] = [{ name: 'молоко', category_name: 'молочные продукты' }]
const SETTINGS: Settings = {
  notify_time: '09:00:00',
  threshold_days: 3,
  horizon_days: 7,
  recommend_limit: 5,
}
const RECIPES: Recipe[] = [
  {
    title: 'Молочный коктейль',
    description: null,
    cooking_time_min: 10,
    ingredients: ['молоко'],
    covered_product_ids: [1],
    covered_ingredients: ['молоко'],
    covered_weight: 5,
  },
]

/** Подписи кнопок всех экранов — на каждом должна быть видна только своя. */
const LABELS = ['Добавить продукт', 'Сохранить', 'Обновить подборку']

// MainButton клиента: приложение не должно её трогать вовсе
const mainButton = {
  setText: vi.fn(),
  setParams: vi.fn(),
  show: vi.fn(),
  hide: vi.fn(),
  enable: vi.fn(),
  disable: vi.fn(),
  showProgress: vi.fn(),
  hideProgress: vi.fn(),
  onClick: vi.fn(),
  offClick: vi.fn(),
}

beforeEach(() => {
  vi.mocked(api.listProducts).mockResolvedValue(PRODUCTS)
  vi.mocked(api.listStoragePlaces).mockResolvedValue(PLACES)
  vi.mocked(api.listIngredients).mockResolvedValue(INGREDIENTS)
  vi.mocked(api.getSettings).mockResolvedValue(SETTINGS)
  vi.mocked(api.getRecommendations).mockResolvedValue(RECIPES)

  // Приложение открыто как бы из клиента Telegram: initData непустая
  window.Telegram = {
    WebApp: {
      initData: 'query_id=test',
      colorScheme: 'dark',
      themeParams: {},
      ready: vi.fn(),
      expand: vi.fn(),
      onEvent: vi.fn(),
      offEvent: vi.fn(),
      showAlert: vi.fn(),
      showConfirm: vi.fn(),
      MainButton: mainButton,
    } as unknown as NonNullable<Window['Telegram']>['WebApp'],
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  delete window.Telegram
})

/** Кнопки действия экрана — по классу, который ставит Screen. */
function screenButtons(): HTMLButtonElement[] {
  return [...document.querySelectorAll<HTMLButtonElement>('.screen-button')]
}

/** Открыт экран с заголовком title, и на нём ровно одна кнопка с подписью label. */
async function expectScreen(title: string, label: string) {
  await screen.findByRole('heading', { level: 1, name: title })

  const buttons = screenButtons()
  expect(buttons).toHaveLength(1)
  expect(buttons[0].textContent).toBe(label)

  // Подписи других экранов не просочились ни в каком виде
  for (const other of LABELS.filter((item) => item !== label)) {
    expect(screen.queryByRole('button', { name: other })).toBeNull()
  }
  expect(screen.getAllByRole('button', { name: label })).toHaveLength(1)
}

describe('кнопка действия экрана', () => {
  it('на каждом экране одна кнопка со своей подписью', async () => {
    render(<App />)
    await expectScreen('Мои продукты', 'Добавить продукт')

    fireEvent.click(screenButtons()[0])
    await expectScreen('Новый продукт', 'Сохранить')

    fireEvent.click(screen.getByRole('button', { name: 'Назад' }))
    await expectScreen('Мои продукты', 'Добавить продукт')

    fireEvent.click(screen.getByRole('tab', { name: 'Рекомендации' }))
    await expectScreen('Рекомендации', 'Обновить подборку')
    await screen.findByText('Молочный коктейль')

    // Тот самый переход, после которого на «Продуктах» висела «Обновить подборку»
    fireEvent.click(screen.getByRole('tab', { name: 'Продукты' }))
    await expectScreen('Мои продукты', 'Добавить продукт')

    fireEvent.click(screen.getByRole('button', { name: 'Настройки' }))
    await expectScreen('Настройки', 'Сохранить')

    // А здесь раньше висела «Добавить продукт»
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }))
    await expectScreen('Мои продукты', 'Добавить продукт')

    fireEvent.click(screen.getByRole('button', { name: /Молоко 3,2 %/ }))
    await expectScreen('Редактирование', 'Сохранить')

    fireEvent.click(screen.getByRole('button', { name: 'Назад' }))
    await expectScreen('Мои продукты', 'Добавить продукт')
  })

  it('к MainButton клиента Telegram приложение не обращается', async () => {
    render(<App />)
    await expectScreen('Мои продукты', 'Добавить продукт')
    fireEvent.click(screen.getByRole('tab', { name: 'Рекомендации' }))
    await expectScreen('Рекомендации', 'Обновить подборку')
    fireEvent.click(screen.getByRole('tab', { name: 'Продукты' }))
    await expectScreen('Мои продукты', 'Добавить продукт')

    for (const method of Object.values(mainButton)) {
      expect(method).not.toHaveBeenCalled()
    }
  })

  it('неактивная «Сохранить» нажимается и называет недостающие поля', async () => {
    render(<App />)
    await expectScreen('Мои продукты', 'Добавить продукт')
    fireEvent.click(screenButtons()[0])
    await expectScreen('Новый продукт', 'Сохранить')

    const save = screenButtons()[0]
    // Неактивность видна, но это не disabled: нажатие должно дойти
    expect(save.classList).toContain('screen-button--inactive')
    expect(save.getAttribute('aria-disabled')).toBe('true')
    expect(save.disabled).toBe(false)

    fireEvent.click(save)

    expect(await screen.findByText('Укажите наименование')).toBeTruthy()
    expect(screen.getByText('Выберите ингредиент из справочника')).toBeTruthy()
    expect(api.createProduct).not.toHaveBeenCalled()
  })

  it('заполненная форма делает кнопку активной и сохраняет', async () => {
    vi.mocked(api.createProduct).mockResolvedValue(PRODUCTS[0])
    render(<App />)
    await expectScreen('Мои продукты', 'Добавить продукт')
    fireEvent.click(screenButtons()[0])
    await expectScreen('Новый продукт', 'Сохранить')

    fireEvent.change(screen.getByPlaceholderText('Молоко 3,2 %'), {
      target: { value: 'Кефир' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: /Ингредиент/ }), {
      target: { value: 'молоко' },
    })

    const save = screenButtons()[0]
    expect(save.classList).not.toContain('screen-button--inactive')
    expect(save.getAttribute('aria-disabled')).toBeNull()

    fireEvent.click(save)

    await expectScreen('Мои продукты', 'Добавить продукт')
    expect(api.createProduct).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Кефир', ingredient_name: 'молоко' }),
    )
  })
})
