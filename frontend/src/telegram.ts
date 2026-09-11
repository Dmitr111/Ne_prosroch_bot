/**
 * Обёртка над SDK Telegram Web Apps.
 *
 * Всё общение с `window.Telegram.WebApp` идёт через этот модуль: initData
 * для авторизации запросов, тема оформления и системные диалоги.
 * Приложение должно открываться и в обычном браузере — при отладке
 * фронтенда клиента Telegram нет, поэтому каждая функция здесь переживает
 * его отсутствие.
 *
 * Основной кнопкой клиента (MainButton) приложение не пользуется: это один
 * глобальный объект на всё приложение, который каждый экран перенастраивал
 * бы императивно, и её вид — отступы, скругление — задаёт клиент, а не мы.
 * Кнопка действия рисуется внутри экрана, см. components/Screen.tsx.
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

export interface TelegramWebApp {
  initData: string
  colorScheme: 'light' | 'dark'
  themeParams: ThemeParams
  ready(): void
  expand(): void
  onEvent(event: string, handler: () => void): void
  offEvent(event: string, handler: () => void): void
  showAlert(message: string): void
  showConfirm(message: string, callback: (confirmed: boolean) => void): void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

/**
 * SDK или null, если приложение открыто вне Telegram.
 *
 * Самого `window.Telegram.WebApp` для этого мало: скрипт SDK создаёт его
 * в любом браузере. Признак запуска из клиента — непустая initData,
 * её передаёт только Telegram.
 */
export function getWebApp(): TelegramWebApp | null {
  const webApp = window.Telegram?.WebApp
  return webApp && webApp.initData ? webApp : null
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

/**
 * Сообщает Telegram о готовности и разворачивает окно на всю высоту.
 *
 * Высоту видимой области SDK сам выставляет в `--tg-viewport-height`
 * и обновляет при открытии клавиатуры — по ней экран держит кнопку
 * действия над клавиатурой.
 */
export function initTelegram(): void {
  const webApp = getWebApp()
  if (!webApp) return

  webApp.ready()
  webApp.expand()
  applyTheme()
  webApp.onEvent('themeChanged', applyTheme)
}

/** Сообщение об ошибке средствами клиента, с запасным вариантом. */
export function showAlert(message: string): void {
  const webApp = getWebApp()
  if (webApp) webApp.showAlert(message)
  else window.alert(message)
}

/** Подтверждение действия средствами клиента, с запасным вариантом. */
export function confirmAction(message: string): Promise<boolean> {
  const webApp = getWebApp()
  if (!webApp) return Promise.resolve(window.confirm(message))
  return new Promise((resolve) => webApp.showConfirm(message, resolve))
}
