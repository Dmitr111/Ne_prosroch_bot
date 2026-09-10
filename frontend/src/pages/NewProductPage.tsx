/**
 * Экран «Новый продукт» (рисунок 2.4, правая часть).
 *
 * Категория отдельным полем не вводится: пользователь выбирает ингредиент
 * из справочника, категория выводится из него. Поэтому список ингредиентов
 * сгруппирован по категориям — так видно, к какой категории попадёт продукт.
 */

import { useMemo, useState } from 'react'
import type { Ingredient, ProductCreate, StoragePlace } from '../api'
import { Field } from '../components/Field'
import { MainButton } from '../components/MainButton'
import { Screen } from '../components/Screen'
import { todayInput } from '../utils/format'

const UNITS = ['шт', 'г', 'кг', 'мл', 'л', 'упак']

interface NewProductPageProps {
  ingredients: Ingredient[]
  places: StoragePlace[]
  saving: boolean
  error: string | null
  onSave: (product: ProductCreate) => void
  onBack: () => void
}

export function NewProductPage({
  ingredients,
  places,
  saving,
  error,
  onSave,
  onBack,
}: NewProductPageProps) {
  const [name, setName] = useState('')
  const [ingredientName, setIngredientName] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [unit, setUnit] = useState(UNITS[0])
  const [manufactureDate, setManufactureDate] = useState('')
  const [expiryDate, setExpiryDate] = useState(todayInput())
  const [placeId, setPlaceId] = useState('')

  const byCategory = useMemo(() => {
    const groups = new Map<string, Ingredient[]>()
    for (const ingredient of ingredients) {
      const group = groups.get(ingredient.category_name)
      if (group) group.push(ingredient)
      else groups.set(ingredient.category_name, [ingredient])
    }
    return [...groups.entries()]
  }, [ingredients])

  const parsedQuantity = Number(quantity.replace(',', '.'))
  const datesValid = !manufactureDate || manufactureDate <= expiryDate
  const valid =
    name.trim().length > 0 &&
    ingredientName.length > 0 &&
    expiryDate.length > 0 &&
    Number.isFinite(parsedQuantity) &&
    parsedQuantity > 0 &&
    datesValid

  function submit() {
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

  return (
    <Screen
      title="Новый продукт"
      onBack={onBack}
      footer={
        <MainButton
          text="Сохранить"
          onClick={submit}
          disabled={!valid}
          progress={saving}
        />
      }
    >
      {error && <p className="notice notice--error">{error}</p>}

      <div className="form">
        <Field label="Наименование">
          <input
            className="control"
            value={name}
            placeholder="Молоко 3,2 %"
            maxLength={255}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        <Field
          label="Ингредиент"
          hint="Категория определяется по выбранному ингредиенту"
        >
          <select
            className="control control--select"
            value={ingredientName}
            onChange={(event) => setIngredientName(event.target.value)}
          >
            <option value="">Выберите из справочника</option>
            {byCategory.map(([category, items]) => (
              <optgroup key={category} label={category}>
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
          <Field label="Количество">
            <input
              className="control"
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
              {UNITS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Дата изготовления">
          <input
            className="control"
            type="date"
            value={manufactureDate}
            onChange={(event) => setManufactureDate(event.target.value)}
          />
        </Field>

        <Field
          label="Годен до"
          hint={datesValid ? undefined : 'Срок годности раньше даты изготовления'}
        >
          <input
            className="control"
            type="date"
            value={expiryDate}
            onChange={(event) => setExpiryDate(event.target.value)}
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
    </Screen>
  )
}
