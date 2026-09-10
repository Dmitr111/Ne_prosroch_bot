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
  isActive: boolean
  isProgressVisible: boolean
  setText(text: string): void
  setParams(params: { text?: string; is_active?: boolean; is_visible?: boolean }): void
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
  showConfirm(message: string, callback: (confirmed: boolean) => void): void
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

/*
 * Основная кнопка.
 *
 * Кнопка у клиента одна на всё приложение, а экраны сменяют друг друга.
 * Прежний вариант при каждой перерисовке и каждой смене экрана посылал
 * клиенту пачку «скрыть → сменить текст → показать», причём от двух
 * экранов вперемешку. Клиент Telegram анимирует скрытие, и текст нового
 * экрана мог не примениться — отсюда «Обновить подборку» на вкладке
 * «Продукты».
 *
 * Теперь состояние кнопки задаётся одним вызовом setParams, обработчик
 * нажатия регистрируется один раз и перенаправляет на текущий, а скрытие
 * при уходе с экрана отложено: если следующий экран сразу занял кнопку,
 * скрывать её не нужно, и клиент получает одно обновление вместо трёх.
 */

export interface MainButtonState {
  text: string
  disabled: boolean
  progress: boolean
}

let owner: symbol | null = null
let handler: (() => void) | null = null
let claims = 0
let listening = false

/**
 * Занимает основную кнопку Telegram под экран и задаёт её состояние.
 *
 * @returns false вне Telegram — тогда экран рисует свою кнопку
 */
export function setMainButton(
  id: symbol,
  state: MainButtonState,
  onClick: () => void,
): boolean {
  const webApp = getWebApp()
  if (!webApp) return false

  const button = webApp.MainButton
  if (!listening) {
    button.onClick(() => handler?.())
    listening = true
  }
  owner = id
  handler = onClick
  claims += 1

  // Прогресс переключается до setParams и только при изменении: hideProgress
  // в SDK включает выключенную кнопку, и после него disable() терялся —
  // «Сохранить» на незаполненной форме выглядела и работала как активная
  if (button.isProgressVisible !== state.progress) {
    if (state.progress) button.showProgress(false)
    else button.hideProgress()
  }
  button.setParams({
    text: state.text,
    is_active: !state.disabled && !state.progress,
    is_visible: true,
  })
  return true
}

/** Освобождает кнопку; скрывает её, только если никто не занял её следом. */
export function releaseMainButton(id: symbol): void {
  const claimsAtRelease = claims
  setTimeout(() => {
    if (owner !== id || claims !== claimsAtRelease) return
    owner = null
    handler = null
    getWebApp()?.MainButton.hide()
  }, 0)
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
