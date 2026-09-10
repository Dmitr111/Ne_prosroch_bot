/**
 * Обёртка над SDK Telegram Web Apps.
 *
 * Всё общение с `window.Telegram.WebApp` идёт через этот модуль: initData
 * для авторизации запросов, тема оформления и основная кнопка. Приложение
 * должно открываться и в обычном браузере — при отладке фронтенда SDK
 * недоступен, поэтому каждая функция здесь переживает его отсутствие.
 */

export interface ThemeParams {
  bg_color?: string
  text_color?: string
  hint_color?: string
  link_color?: string
  button_color?: string
  button_text_color?: string
  secondary_bg_color?: string
  section_bg_color?: string
  section_header_text_color?: string
  subtitle_text_color?: string
  destructive_text_color?: string
  accent_text_color?: string
}

export interface MainButton {
  text: string
  isVisible: boolean
  setText(text: string): void
  show(): void
  hide(): void
  enable(): void
  disable(): void
  showProgress(leaveActive?: boolean): void
  hideProgress(): void
  onClick(handler: () => void): void
  offClick(handler: () => void): void
}

export interface TelegramWebApp {
  initData: string
  colorScheme: 'light' | 'dark'
  themeParams: ThemeParams
  MainButton: MainButton
  ready(): void
  expand(): void
  onEvent(event: string, handler: () => void): void
  offEvent(event: string, handler: () => void): void
  showAlert(message: string): void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

/** SDK или null, если приложение открыто вне Telegram. */
export function getWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null
}

/**
 * Подписанная строка initData для заголовка авторизации.
 *
 * Вне Telegram возвращается пустая строка: сервер ответит 401, и это
 * правильное поведение — без подписи доступа к данным нет.
 */
export function getInitData(): string {
  return getWebApp()?.initData ?? ''
}

/**
 * Переносит параметры темы в CSS-переменные.
 *
 * Свежие версии SDK выставляют `--tg-theme-*` сами, но не все клиенты
 * это делают, поэтому переменные проставляются здесь ещё раз — из
 * `themeParams`. Цвета фона, текста и кнопок нигде в стилях не зашиты,
 * приложение подхватывает и светлую, и тёмную тему.
 */
export function applyTheme(): void {
  const webApp = getWebApp()
  if (!webApp) return

  const root = document.documentElement
  for (const [name, value] of Object.entries(webApp.themeParams)) {
    if (typeof value === 'string') {
      root.style.setProperty(`--tg-theme-${name.replace(/_/g, '-')}`, value)
    }
  }
  root.dataset.colorScheme = webApp.colorScheme
}

/** Сообщает Telegram о готовности и разворачивает окно на всю высоту. */
export function initTelegram(): void {
  const webApp = getWebApp()
  if (!webApp) return

  webApp.ready()
  webApp.expand()
  applyTheme()
  webApp.onEvent('themeChanged', applyTheme)
}

/**
 * Показывает основную кнопку Telegram и возвращает функцию отписки.
 *
 * Вне Telegram возвращает null — вызывающий код рисует свою кнопку
 * в потоке страницы, как на макетах.
 */
export function showMainButton(
  text: string,
  onClick: () => void,
  options: { disabled?: boolean; progress?: boolean } = {},
): (() => void) | null {
  const webApp = getWebApp()
  if (!webApp) return null

  const button = webApp.MainButton
  button.setText(text)
  if (options.disabled) button.disable()
  else button.enable()
  if (options.progress) button.showProgress(false)
  else button.hideProgress()
  button.onClick(onClick)
  button.show()

  return () => {
    button.offClick(onClick)
    button.hide()
    button.hideProgress()
  }
}

/** Сообщение об ошибке средствами клиента, с запасным вариантом. */
export function showAlert(message: string): void {
  const webApp = getWebApp()
  if (webApp) webApp.showAlert(message)
  else window.alert(message)
}
