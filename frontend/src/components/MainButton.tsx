/**
 * Основная кнопка экрана.
 *
 * Внутри Telegram используется штатная MainButton клиента, вне его —
 * кнопка в потоке страницы, как на макетах. Иначе при отладке в браузере
 * действие экрана было бы недоступно.
 *
 * Обработчик нажатия хранится в ref: экраны передают новую функцию при
 * каждой перерисовке, и если бы она попадала в зависимости эффекта,
 * кнопка переподключалась бы на каждый рендер.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getWebApp, releaseMainButton, setMainButton } from '../telegram'

interface MainButtonProps {
  text: string
  onClick: () => void
  disabled?: boolean
  progress?: boolean
}

export function MainButton({ text, onClick, disabled = false, progress = false }: MainButtonProps) {
  const insideTelegram = getWebApp() !== null
  const [id] = useState(() => Symbol('main-button'))
  const handlerRef = useRef(onClick)

  useLayoutEffect(() => {
    handlerRef.current = onClick
  })

  useEffect(() => {
    if (!insideTelegram) return
    setMainButton(id, { text, disabled, progress }, () => handlerRef.current())
  }, [insideTelegram, id, text, disabled, progress])

  useEffect(() => {
    if (!insideTelegram) return
    return () => releaseMainButton(id)
  }, [insideTelegram, id])

  if (insideTelegram) return null

  return (
    <button className="main-button" onClick={onClick} disabled={disabled || progress}>
      {progress ? 'Подождите…' : text}
    </button>
  )
}
