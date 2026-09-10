/**
 * Экран «Настройки» (рисунок 2.5, правая часть).
 *
 * Время отправки и порог оповещения относятся к напоминаниям, горизонт
 * планирования T и число рецептов k — к подбору. Названия полей API:
 * notify_time, threshold_days, horizon_days, recommend_limit.
 *
 * Время отправки выбирается с точностью до часа, списком 00:00–23:00.
 * Рассылка запускается ежечасно и отбирает получателей по часу, минуты
 * планировщик не учитывает: выбранные 23:25 молча превращались в 23:00.
 * Заодно список, в отличие от <input type="time">, не зависит от локали
 * устройства — 24-часовой формат виден и на телефоне с английской системой.
 */

import { useState } from 'react'
import type { Settings } from '../api'
import { MainButton } from '../components/MainButton'
import { Screen } from '../components/Screen'
import { formatDays, formatHour, hourOf, hourToApi } from '../utils/format'

const HOURS = Array.from({ length: 24 }, (_, hour) => hour)
const THRESHOLD_OPTIONS = [1, 2, 3, 5, 7, 10, 14, 30]
const HORIZON_OPTIONS = [1, 3, 5, 7, 10, 14, 21, 30, 60]
const LIMIT_OPTIONS = [1, 2, 3, 4, 5, 7, 10, 15, 20]

/**
 * Варианты списка вместе с текущим значением.
 *
 * Если сохранённое значение не входит в стандартный набор, select молча
 * показал бы первый вариант, и «Сохранить» затёрло бы настройку.
 */
function withCurrent(options: number[], current: number): number[] {
  return options.includes(current)
    ? options
    : [...options, current].sort((a, b) => a - b)
}

interface SettingsPageProps {
  settings: Settings
  saving: boolean
  error: string | null
  onSave: (changes: Settings) => void
  onBack: () => void
}

export function SettingsPage({ settings, saving, error, onSave, onBack }: SettingsPageProps) {
  const [notifyHour, setNotifyHour] = useState(hourOf(settings.notify_time))
  const [thresholdDays, setThresholdDays] = useState(settings.threshold_days)
  const [horizonDays, setHorizonDays] = useState(settings.horizon_days)
  const [recommendLimit, setRecommendLimit] = useState(settings.recommend_limit)

  return (
    <Screen
      title="Настройки"
      onBack={onBack}
      footer={
        <MainButton
          text="Сохранить"
          onClick={() =>
            onSave({
              notify_time: hourToApi(notifyHour),
              threshold_days: thresholdDays,
              horizon_days: horizonDays,
              recommend_limit: recommendLimit,
            })
          }
          progress={saving}
        />
      }
    >
      {error && <p className="notice notice--error">{error}</p>}

      <h2 className="group__title">НАПОМИНАНИЯ</h2>
      <div className="card-list">
        <label className="card row">
          <span className="row__label">Время отправки</span>
          <select
            className="row__control"
            value={notifyHour}
            onChange={(event) => setNotifyHour(Number(event.target.value))}
          >
            {HOURS.map((hour) => (
              <option key={hour} value={hour}>
                {formatHour(hour)}
              </option>
            ))}
          </select>
        </label>
        <label className="card row">
          <span className="row__label">Напоминать за</span>
          <select
            className="row__control"
            value={thresholdDays}
            onChange={(event) => setThresholdDays(Number(event.target.value))}
          >
            {withCurrent(THRESHOLD_OPTIONS, settings.threshold_days).map((days) => (
              <option key={days} value={days}>
                {formatDays(days)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <h2 className="group__title">ПОДБОР РЕЦЕПТОВ</h2>
      <div className="card-list">
        <label className="card row">
          <span className="row__label">Горизонт планирования</span>
          <select
            className="row__control"
            value={horizonDays}
            onChange={(event) => setHorizonDays(Number(event.target.value))}
          >
            {withCurrent(HORIZON_OPTIONS, settings.horizon_days).map((days) => (
              <option key={days} value={days}>
                {formatDays(days)}
              </option>
            ))}
          </select>
        </label>
        <label className="card row">
          <span className="row__label">Рецептов в подборке</span>
          <select
            className="row__control"
            value={recommendLimit}
            onChange={(event) => setRecommendLimit(Number(event.target.value))}
          >
            {withCurrent(LIMIT_OPTIONS, settings.recommend_limit).map((count) => (
              <option key={count} value={count}>
                {count}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="footnote footnote--left">
        Напоминание приходит в начале выбранного часа. В подборе участвуют
        продукты, срок годности которых истекает в пределах горизонта.
      </p>
    </Screen>
  )
}
