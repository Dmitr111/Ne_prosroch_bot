/**
 * Основная кнопка экрана.
 *
 * Внутри Telegram используется штатная MainButton клиента, вне его —
 * кнопка в потоке страницы, как на макетах. Иначе при отладке в браузере
 * действие экрана было бы недоступно.
 */

import { useEffect } from 'react'
import { getWebApp, showMainButton } from '../telegram'

interface MainButtonProps {
  text: string
  onClick: () => void
  disabled?: boolean
  progress?: boolean
}

export function MainButton({ text, onClick, disabled, progress }: MainButtonProps) {
  const insideTelegram = getWebApp() !== null

  useEffect(() => {
    if (!insideTelegram) return
    return showMainButton(text, onClick, { disabled, progress }) ?? undefined
  }, [insideTelegram, text, onClick, disabled, progress])

  if (insideTelegram) return null

  return (
    <button className="main-button" onClick={onClick} disabled={disabled || progress}>
      {progress ? 'Подождите…' : text}
    </button>
  )
}
