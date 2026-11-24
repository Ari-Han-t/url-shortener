import type { ClickEvent } from '../api'
import { parseTimestamp } from './format'

export interface DayCount {
  date: Date
  count: number
}

export interface BreakdownRow {
  label: string
  count: number
}

/** Click counts per local calendar day for the last `days` days, oldest first. */
export function clicksByDay(history: ClickEvent[], days = 14): DayCount[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const buckets: DayCount[] = []
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(today.getDate() - i)
    buckets.push({ date: d, count: 0 })
  }
  const start = buckets[0].date.getTime()
  for (const ev of history) {
    const t = parseTimestamp(ev.timestamp)
    if (!t) continue
    const day = new Date(t)
    day.setHours(0, 0, 0, 0)
    const idx = Math.round((day.getTime() - start) / 86_400_000)
    if (idx >= 0 && idx < days) buckets[idx].count += 1
  }
  return buckets
}

export function breakdown(
  history: ClickEvent[],
  pick: (e: ClickEvent) => string,
  limit = 5,
): BreakdownRow[] {
  const counts = new Map<string, number>()
  for (const ev of history) {
    const label = pick(ev) || 'Unknown'
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, limit)
}
