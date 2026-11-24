export type ExpiryChoice = 'keep' | 'never' | '1' | '7' | '30' | 'custom'

const DAY = 86_400_000

export interface ExpiryResult {
  /** undefined: leave unchanged, null: no expiry, string: ISO time. */
  value: string | null | undefined
  error?: string
}

/** The value (ISO time) to send for a choice, or an error message. */
export function expiryFromChoice(choice: ExpiryChoice, customDate: string, now = new Date()): ExpiryResult {
  switch (choice) {
    case 'keep':
      return { value: undefined }
    case 'never':
      return { value: null }
    case 'custom': {
      if (!customDate) return { value: undefined, error: 'Pick an expiry date.' }
      // End of the chosen day in the user's time zone.
      const end = new Date(`${customDate}T23:59:59`)
      if (Number.isNaN(end.getTime())) return { value: undefined, error: 'That date is not valid.' }
      if (end.getTime() <= now.getTime()) return { value: undefined, error: 'The expiry date must be in the future.' }
      if (end.getTime() > now.getTime() + 5 * 365 * DAY) {
        return { value: undefined, error: 'The expiry can be at most 5 years away.' }
      }
      return { value: end.toISOString() }
    }
    default:
      return { value: new Date(now.getTime() + Number(choice) * DAY).toISOString() }
  }
}

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'}`
}

/** "Expires in 3 days", "Expired 2 hours ago". */
export function describeExpiry(expiresAt: string, now = new Date()): string {
  const diff = new Date(expiresAt).getTime() - now.getTime()
  const abs = Math.abs(diff)
  let span: string
  if (abs < 3_600_000) span = plural(Math.max(1, Math.round(abs / 60_000)), 'minute')
  else if (abs < 2 * DAY) span = plural(Math.round(abs / 3_600_000), 'hour')
  else span = plural(Math.round(abs / DAY), 'day')
  return diff > 0 ? `Expires in ${span}` : `Expired ${span} ago`
}

/** Local YYYY-MM-DD for the date input's min attribute. */
export function todayInputValue(now = new Date()): string {
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${m}-${d}`
}
