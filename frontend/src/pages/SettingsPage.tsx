/**
 * Экран «Настройки» (рисунок 2.5, правая часть).
 *
 * Время отправки и порог оповещения относятся к напоминаниям, горизонт
 * планирования T и число рецептов k — к подбору. Названия полей API:
 * notify_time, threshold_days, horizon_days, recommend_limit.
 */

import { useState } from 'react'
import type { Settings } from '../api'
import { MainButton } from '../components/MainButton'
import { Screen } from '../components/Screen'
import { formatDays, timeToInput } from '../utils/format'

interface SettingsPageProps {
  settings: Settings
  saving: boolean
  error: string | null
  onSave: (changes: Settings) => void
  onBack: () => void
}

export function SettingsPage({ settings, saving, error, onSave, onBack }: SettingsPageProps) {
  const [notifyTime, setNotifyTime] = useState(timeToInput(settings.notify_time))
  const [thresholdDays, setThresholdDays] = useState(settings.threshold_days)
  const [horizonDays, setHorizonDays] = useState(settings.horizon_days)
  const [recommendLimit, setRecommendLimit] = useState(settings.recommend_limit)

  const valid = notifyTime.length >= 4

  return (
    <Screen
      title="Настройки"
      onBack={onBack}
      footer={
        <MainButton
          text="Сохранить"
          onClick={() =>
            onSave({
              notify_time: `${notifyTime}:00`,
              threshold_days: thresholdDays,
              horizon_days: horizonDays,
              recommend_limit: recommendLimit,
            })
          }
          disabled={!valid}
          progress={saving}
        />
      }
    >
      {error && <p className="notice notice--error">{error}</p>}

      <h2 className="group__title">НАПОМИНАНИЯ</h2>
      <div className="card-list">
        <label className="card row">
          <span className="row__label">Время отправки</span>
          <input
            className="row__control"
            type="time"
            value={notifyTime}
            onChange={(event) => setNotifyTime(event.target.value)}
          />
        </label>
        <label className="card row">
          <span className="row__label">Напоминать за</span>
          <select
            className="row__control"
            value={thresholdDays}
            onChange={(event) => setThresholdDays(Number(event.target.value))}
          >
            {[1, 2, 3, 5, 7, 10, 14, 30].map((days) => (
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
            {[1, 3, 5, 7, 10, 14, 21, 30, 60].map((days) => (
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
            {[1, 2, 3, 4, 5, 7, 10, 15, 20].map((count) => (
              <option key={count} value={count}>
                {count}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="footnote footnote--left">
        В подборе участвуют продукты, срок годности которых истекает в пределах
        горизонта.
      </p>
    </Screen>
  )
}
