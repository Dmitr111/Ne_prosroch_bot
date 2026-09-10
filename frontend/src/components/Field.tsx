/** Поле формы с подписью — как на макете «Новый продукт». */

import type { ReactNode } from 'react'

interface FieldProps {
  label: string
  children: ReactNode
  hint?: string
  /** Ошибка заменяет подсказку, пока не исправлена */
  error?: string
}

export function Field({ label, children, hint, error }: FieldProps) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {error ? (
        <span className="field__hint field__hint--error">{error}</span>
      ) : (
        hint && <span className="field__hint">{hint}</span>
      )}
    </label>
  )
}
