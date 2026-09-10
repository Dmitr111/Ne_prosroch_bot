/** Форматирование остаточного срока и количества на русском. */

/** Склонение существительного при числительном. */
function plural(count: number, one: string, few: string, many: string): string {
  const tail = Math.abs(count) % 100
  if (tail >= 11 && tail <= 14) return many
  switch (Math.abs(count) % 10) {
    case 1:
      return one
    case 2:
    case 3:
    case 4:
      return few
    default:
      return many
  }
}

/**
 * Остаточный срок словами, как на макете: «сегодня», «2 дня», «160 дней».
 * Отрицательный срок означает просрочку.
 */
export function formatDaysLeft(daysLeft: number): string {
  if (daysLeft === 0) return 'сегодня'
  if (daysLeft < 0) {
    const days = Math.abs(daysLeft)
    return `просрочено на ${days} ${plural(days, 'день', 'дня', 'дней')}`
  }
  return `${daysLeft} ${plural(daysLeft, 'день', 'дня', 'дней')}`
}

/** Короткая пометка для перечня истекающих продуктов. */
export function formatExpiryHint(daysLeft: number): string {
  if (daysLeft === 0) return 'сегодня'
  if (daysLeft < 0) return 'просрочено'
  return formatDaysLeft(daysLeft)
}

/** Количество без лишних нулей: 0.4 → «0,4», 1 → «1». */
export function formatQuantity(quantity: number): string {
  return String(Number(quantity.toFixed(3))).replace('.', ',')
}

/** Число дней с существительным — для экрана настроек. */
export function formatDays(days: number): string {
  return `${days} ${plural(days, 'день', 'дня', 'дней')}`
}

/*
 * Даты и время форматируются здесь вручную, а не средствами браузера.
 * Нативные <input type="date|time"> в WebView Telegram показывают значение
 * в локали устройства и атрибут lang="ru" не учитывают: на телефоне
 * с английской системой получалось 09/10/2026 и 11:25 PM. Разбор строки
 * без new Date() заодно избавляет от сдвига на сутки из-за часового пояса.
 */

/** Дата из API (YYYY-MM-DD) в русском формате: 10.09.2026. */
export function formatDate(value: string): string {
  const [year, month, day] = value.split('-')
  return year && month && day ? `${day}.${month}.${year}` : value
}

/** Час напоминания из времени API (HH:MM:SS): 23. */
export function hourOf(value: string): number {
  return Number(value.slice(0, 2)) || 0
}

/** Час в 24-часовом формате: 9 → «09:00». */
export function formatHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

/** Час в формат времени API: 9 → «09:00:00». */
export function hourToApi(hour: number): string {
  return `${formatHour(hour)}:00`
}

/** Сегодняшняя дата в формате поля ввода. */
export function todayInput(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}
