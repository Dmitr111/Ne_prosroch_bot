/** Каркас экрана: шапка с заголовком, прокручиваемое содержимое, кнопка внизу. */

import type { ReactNode } from 'react'

interface ScreenProps {
  title: string
  onBack?: () => void
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

export function Screen({ title, onBack, actions, children, footer }: ScreenProps) {
  return (
    <div className="screen">
      <header className="screen__header">
        <div className="screen__side">
          {onBack && (
            <button className="icon-button" onClick={onBack} aria-label="Назад">
              <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
                <path
                  d="M15 5 L8 12 L15 19"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </div>
        <h1 className="screen__title">{title}</h1>
        <div className="screen__side screen__side--end">{actions}</div>
      </header>

      <main className="screen__body">{children}</main>

      {footer}
    </div>
  )
}
