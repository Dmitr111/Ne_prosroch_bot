/**
 * Каркас экрана: шапка с заголовком, прокручиваемое содержимое, кнопка внизу.
 *
 * Кнопка действия принадлежит экрану: она описывается параметром `button`,
 * рисуется здесь же и монтируется и размонтируется вместе с экраном.
 * Глобального состояния у неё нет, поэтому подпись одного экрана не может
 * остаться висеть на другом. Параметр обязательный и одиночный — у каждого
 * экрана ровно одна такая кнопка.
 *
 * Раскладка — колонка на высоту видимой области: шапка, прокручиваемое
 * содержимое и подвал с кнопкой. Прокручивается только середина, поэтому
 * кнопка всегда внизу и не перекрывает последний элемент списка, а когда
 * клавиатура уменьшает видимую область, подвал поднимается вместе с ней.
 */

import type { ReactNode } from 'react'

export interface ScreenButton {
  text: string
  onClick: () => void
  /**
   * Выглядит неактивной, но нажатие проходит: экран сам объясняет,
   * чего не хватает. Настоящий disabled глушил бы нажатие молча
   */
  inactive?: boolean
  /** Идёт запрос: повторное нажатие блокируется */
  progress?: boolean
}

interface ScreenProps {
  title: string
  onBack?: () => void
  actions?: ReactNode
  button: ScreenButton
  children: ReactNode
}

export function Screen({ title, onBack, actions, button, children }: ScreenProps) {
  const { text, onClick, inactive = false, progress = false } = button

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

      <footer className="screen__footer">
        <button
          type="button"
          className={`screen-button ${inactive ? 'screen-button--inactive' : ''}`}
          aria-disabled={inactive || undefined}
          aria-busy={progress || undefined}
          disabled={progress}
          onClick={onClick}
        >
          {text}
        </button>
      </footer>
    </div>
  )
}
