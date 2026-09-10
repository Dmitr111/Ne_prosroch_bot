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

/** Время из ответа API (HH:MM:SS) в значение поля ввода (HH:MM). */
export function timeToInput(value: string): string {
  return value.slice(0, 5)
}

/** Сегодняшняя дата в формате поля ввода. */
export function todayInput(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}
