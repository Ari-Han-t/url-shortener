import type { DayCount } from '../lib/analytics'

const W = 560
const H = 120
const GAP = 6

const dayFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })

/** Plain SVG column chart of clicks per day. */
export function BarChart({ days }: { days: DayCount[] }) {
  const max = Math.max(1, ...days.map((d) => d.count))
  const total = days.reduce((s, d) => s + d.count, 0)
  const barW = (W - GAP * (days.length - 1)) / days.length
  const first = dayFmt.format(days[0].date)
  const last = dayFmt.format(days[days.length - 1].date)

  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block h-32 w-full"
        role="img"
        aria-label={`Clicks per day, ${first} to ${last}: ${total} in total`}
        preserveAspectRatio="none"
      >
        <line x1="0" x2={W} y1={H - 0.5} y2={H - 0.5} stroke="var(--line)" strokeWidth="1" />
        {days.map((d, i) => {
          const h = d.count === 0 ? 2 : Math.max(4, (d.count / max) * (H - 8))
          return (
            <rect
              key={d.date.getTime()}
              x={i * (barW + GAP)}
              y={H - h}
              width={barW}
              height={h}
              rx="2"
              fill={d.count === 0 ? 'var(--line)' : 'var(--accent)'}
            >
              <title>{`${dayFmt.format(d.date)}: ${d.count} ${d.count === 1 ? 'click' : 'clicks'}`}</title>
            </rect>
          )
        })}
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-muted">
        <span>{first}</span>
        <span>peak {max === 1 && total === 0 ? 0 : max} per day</span>
        <span>{last}</span>
      </figcaption>
    </figure>
  )
}
