import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './styles.css'
import { initTelegram } from './telegram'

// Тема применяется до первой отрисовки, иначе в тёмном клиенте на мгновение
// мелькнул бы светлый фон
initTelegram()

const container = document.getElementById('root')
if (!container) throw new Error('не найден корневой элемент #root')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
