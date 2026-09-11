/**
 * Экран «Новый продукт» (рисунок 2.4, правая часть) и редактирование.
 *
 * Одна форма на оба случая: при редактировании поля заполнены значениями
 * продукта, а внизу добавлены отметки «использован», «списан» и удаление
 * из перечня. Эндпоинты для этого есть давно (PATCH, POST .../status,
 * DELETE), не хватало только экрана.
 *
 * Категория отдельным полем не вводится: пользователь выбирает ингредиент
 * из справочника, категория выводится из него и показывается под полем,
 * чтобы ошибочный выбор был виден до сохранения.
 */

import { useMemo, useState } from 'react'
import type { Ingredient, Product, ProductCreate, StatusCode, StoragePlace } from '../api'
import { DateField } from '../components/DateField'
import { Field } from '../components/Field'
import { Screen } from '../components/Screen'
import { confirmAction } from '../telegram'
import { formatQuantity, todayInput } from '../utils/format'

const UNITS = ['шт', 'г', 'кг', 'мл', 'л', 'упак']

interface ProductFormPageProps {
  /** Продукт для редактирования; без него форма создаёт новый */
  product?: Product
  ingredients: Ingredient[]
  places: StoragePlace[]
  saving: boolean
  error: string | null
  onSave: (values: ProductCreate) => void
  onSetStatus?: (status: StatusCode) => void
  onRemove?: () => void
  onBack: () => void
}

export function ProductFormPage({
  product,
  ingredients,
  places,
  saving,
  error,
  onSave,
  onSetStatus,
  onRemove,
  onBack,
}: ProductFormPageProps) {
  const [name, setName] = useState(product?.name ?? '')
  const [ingredientName, setIngredientName] = useState(product?.ingredient_name ?? '')
  const [quantity, setQuantity] = useState(
    product ? formatQuantity(product.quantity) : '1',
  )
  const [unit, setUnit] = useState(product?.unit ?? UNITS[0])
  const [manufactureDate, setManufactureDate] = useState(product?.manufacture_date ?? '')
  const [expiryDate, setExpiryDate] = useState(product?.expiry_date ?? todayInput())
  const [placeId, setPlaceId] = useState(
    product?.storage_place_id != null ? String(product.storage_place_id) : '',
  )
  // Ошибки показываются после первой попытки сохранить, а не с порога
  const [attempted, setAttempted] = useState(false)

  const categoryOf = useMemo(
    () => new Map(ingredients.map((item) => [item.name, item.category_name])),
    [ingredients],
  )

  const byCategory = useMemo(() => {
    const groups = new Map<string, Ingredient[]>()
    for (const ingredient of ingredients) {
      const group = groups.get(ingredient.category_name)
      if (group) group.push(ingredient)
      else groups.set(ingredient.category_name, [ingredient])
    }
    // Категории по алфавиту: раньше порядок групп задавал первый по алфавиту
    // ингредиент, и список открывался «овощами и фруктами»
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, 'ru'))
  }, [ingredients])

  // У продукта может быть единица не из стандартного списка
  const units = UNITS.includes(unit) ? UNITS : [...UNITS, unit]

  const parsedQuantity = Number(quantity.replace(',', '.'))
  const errors = {
    name: name.trim() ? null : 'Укажите наименование',
    ingredient: ingredientName ? null : 'Выберите ингредиент из справочника',
    quantity:
      Number.isFinite(parsedQuantity) && parsedQuantity > 0
        ? null
        : 'Количество должно быть больше нуля',
    expiry: !expiryDate
      ? 'Укажите срок годности'
      : manufactureDate && manufactureDate > expiryDate
        ? 'Срок годности раньше даты изготовления'
        : null,
  }
  const valid = Object.values(errors).every((message) => message === null)

  // Пока форма не заполнена, кнопка выглядит неактивной, но нажатие не глохнет:
  // оно показывает, каких полей не хватает. Молчащая кнопка оставляла
  // пользователя в недоумении
  function submit() {
    setAttempted(true)
    if (!valid) return
    onSave({
      name: name.trim(),
      expiry_date: expiryDate,
      manufacture_date: manufactureDate || null,
      ingredient_name: ingredientName,
      storage_place_id: placeId ? Number(placeId) : null,
      quantity: parsedQuantity,
      unit,
    })
  }

  async function markWrittenOff() {
    if (await confirmAction('Продукт испортился? Он попадёт в статистику потерь.')) {
      onSetStatus?.('written_off')
    }
  }

  async function remove() {
    if (await confirmAction('Удалить позицию из перечня? Это для ошибочно внесённых продуктов.')) {
      onRemove?.()
    }
  }

  const category = ingredientName ? categoryOf.get(ingredientName) : undefined
  const show = (message: string | null) => (attempted ? (message ?? undefined) : undefined)

  return (
    <Screen
      title={product ? 'Редактирование' : 'Новый продукт'}
      onBack={onBack}
      button={{ text: 'Сохранить', onClick: submit, inactive: !valid, progress: saving }}
    >
      {error && <p className="notice notice--error">{error}</p>}

      <div className="form">
        <Field label="Наименование" error={show(errors.name)}>
          <input
            className={`control ${attempted && errors.name ? 'control--invalid' : ''}`}
            value={name}
            placeholder="Молоко 3,2 %"
            maxLength={255}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        <Field
          label="Ингредиент"
          error={show(errors.ingredient)}
          hint={
            category
              ? `Категория: ${category}`
              : 'Категория определяется по выбранному ингредиенту'
          }
        >
          <select
            className={`control control--select ${
              attempted && errors.ingredient ? 'control--invalid' : ''
            } ${ingredientName ? '' : 'control--placeholder'}`}
            value={ingredientName}
            onChange={(event) => setIngredientName(event.target.value)}
          >
            {/* Подсказка, а не вариант выбора: disabled и hidden убирают её
                из списка, но оставляют видимой в пустом поле */}
            <option value="" disabled hidden>
              Выберите из справочника
            </option>
            {byCategory.map(([categoryName, items]) => (
              <optgroup key={categoryName} label={categoryName}>
                {items.map((ingredient) => (
                  <option key={ingredient.name} value={ingredient.name}>
                    {ingredient.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>

        <div className="form__row">
          <Field label="Количество" error={show(errors.quantity)}>
            <input
              className={`control ${attempted && errors.quantity ? 'control--invalid' : ''}`}
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </Field>
          <Field label="Единица">
            <select
              className="control control--select"
              value={unit}
              onChange={(event) => setUnit(event.target.value)}
            >
              {units.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Дата изготовления">
          <DateField value={manufactureDate} onChange={setManufactureDate} clearable />
        </Field>

        <Field label="Годен до" error={show(errors.expiry)}>
          <DateField
            value={expiryDate}
            onChange={setExpiryDate}
            placeholder="Выберите дату"
            invalid={attempted && errors.expiry !== null}
          />
        </Field>

        <Field label="Место хранения">
          <select
            className="control control--select"
            value={placeId}
            onChange={(event) => setPlaceId(event.target.value)}
          >
            <option value="">Не указано</option>
            {places.map((place) => (
              <option key={place.id} value={place.id}>
                {place.name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {product && (
        <div className="actions">
          <button
            className="action"
            disabled={saving}
            onClick={() => onSetStatus?.('used')}
          >
            Отметить использованным
          </button>
          <button className="action" disabled={saving} onClick={() => void markWrittenOff()}>
            Списать как испорченный
          </button>
          <button
            className="action action--danger"
            disabled={saving}
            onClick={() => void remove()}
          >
            Удалить из перечня
          </button>
          <p className="field__hint">
            Удаление — для ошибочно внесённых позиций, в статистику потерь оно
            не попадает. Испортившийся продукт отмечайте как списанный.
          </p>
        </div>
      )}
    </Screen>
  )
}
