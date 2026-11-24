import type { BreakdownRow } from '../lib/analytics'
import { nf } from '../lib/format'

export function BreakdownList({ title, rows }: { title: string; rows: BreakdownRow[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <section aria-label={title}>
      <h4 className="mb-2 text-sm font-medium">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No data yet.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.label} className="text-sm">
              <div className="flex justify-between gap-3">
                <span className="truncate" title={r.label}>
                  {r.label}
                </span>
                <span className="tabular-nums text-muted">{nf.format(r.count)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-sunken" aria-hidden="true">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(r.count / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
