/**
 * Поле даты с русским форматом отображения.
 *
 * Нативный <input type="date"> показывает значение в локали устройства,
 * поэтому видимый текст рисуется свой (10.09.2026), а сам input лежит
 * поверх прозрачным слоем: касание открывает штатный календарь телефона.
 * Сам календарь остаётся в языке системы — управлять им со страницы нельзя.
 */

import type { MouseEvent } from 'react'
import { formatDate } from '../utils/format'

interface DateFieldProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  /** Необязательную дату можно стереть — у нативного поля на Android такой кнопки нет */
  clearable?: boolean
  invalid?: boolean
}

export function DateField({
  value,
  onChange,
  placeholder = 'Не указана',
  clearable = false,
  invalid = false,
}: DateFieldProps) {
  // На компьютере клик по невидимому полю лишь ставит курсор в его сегменты,
  // календарь открывается явно
  function openPicker(event: MouseEvent<HTMLInputElement>) {
    try {
      event.currentTarget.showPicker?.()
    } catch {
      // Браузер без showPicker откроет календарь сам
    }
  }

  return (
    <div className={`control date-control ${invalid ? 'control--invalid' : ''}`}>
      <span className={value ? '' : 'date-control__placeholder'}>
        {value ? formatDate(value) : placeholder}
      </span>
      <input
        className="date-control__input"
        type="date"
        value={value}
        onClick={openPicker}
        onChange={(event) => onChange(event.target.value)}
      />
      {clearable && value && (
        <button
          type="button"
          className="date-control__clear"
          aria-label="Очистить дату"
          onClick={(event) => {
            event.preventDefault()
            onChange('')
          }}
        >
          ×
        </button>
      )}
    </div>
  )
}
