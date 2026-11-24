import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  downloadClicks,
  shortLink,
  type AnalyticsData,
  type CountRow,
  type ExportFormat,
} from '../api'
import { useAnalytics } from '../hooks/useAnalytics'
import { breakdown, clicksByDay } from '../lib/analytics'
import { displayLink, nf, parseTimestamp } from '../lib/format'
import { btnSecondary } from '../lib/ui'
import { BarChart } from './BarChart'
import { BreakdownList } from './BreakdownList'
import { Modal } from './Modal'

const whenFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

type Tab = 'overview' | 'audience' | 'sources'
const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'audience', label: 'Audience' },
  { id: 'sources', label: 'Sources' },
]

const rows = (list: CountRow[], format?: (r: CountRow) => string) =>
  list.map((r) => ({ label: format ? format(r) : r.name, count: r.clicks }))

export function AnalyticsPanel({ shortId, onClose }: { shortId: string | null; onClose: () => void }) {
  const { data, error, loading } = useAnalytics(shortId)

  return (
    <Modal open={shortId !== null} title="Analytics" onClose={onClose} variant="drawer">
      {shortId && (
        <div className="flex flex-col gap-6">
          <div className="min-w-0">
            <p className="break-all font-mono text-sm font-medium">{displayLink(shortLink(shortId))}</p>
            {data && (
              <p className="truncate text-sm text-muted" title={data.longUrl}>
                {data.longUrl}
              </p>
            )}
          </div>
          {loading && <p className="text-sm text-muted">Loading analytics...</p>}
          {error && <p className="text-sm text-danger">{error}</p>}
          {data && <AnalyticsBody data={data} />}
          {data && <ExportButtons shortId={data.shortId} />}
          <p className="border-t border-line pt-4 text-xs text-muted">
            Location is looked up offline at city level and the IP address is not stored. IP geolocation by{' '}
            <a className="underline underline-offset-2 hover:text-ink" href="https://db-ip.com" target="_blank" rel="noreferrer">
              DB-IP
            </a>
            .
          </p>
        </div>
      )}
    </Modal>
  )
}

function AnalyticsBody({ data }: { data: AnalyticsData }) {
  const [tab, setTab] = useState<Tab>('overview')
  const { days, devices, systems, browsers, recent } = useMemo(
    () => ({
      days: clicksByDay(data.history, 14),
      devices: breakdown(data.history, (e) => e.deviceType),
      systems: breakdown(data.history, (e) => e.os),
      browsers: breakdown(data.history, (e) => e.browser),
      recent: data.history.slice(0, 10),
    }),
    [data],
  )
  const s = data.summary
  const truncated = data.totalClicks > data.history.length

  if (data.totalClicks === 0 && data.history.length === 0 && s.botHits === 0) {
    return (
      <p className="rounded-md bg-sunken p-4 text-sm text-muted">
        No clicks yet. Open or share the short link and the first click will show up here.
      </p>
    )
  }

  return (
    <>
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <div>
          <p className="text-3xl font-semibold tabular-nums">{nf.format(data.totalClicks)}</p>
          <p className="text-sm text-muted">clicks</p>
        </div>
        <div>
          <p className="text-3xl font-semibold tabular-nums">{nf.format(s.uniqueVisitors)}</p>
          <p className="text-sm text-muted">unique visitors, counted per day</p>
        </div>
      </div>
      <p className="-mt-3 text-xs text-muted">
        Bots and link previews are not counted
        {s.botHits > 0 ? `: ${nf.format(s.botHits)} bot or preview ${s.botHits === 1 ? 'hit' : 'hits'} so far.` : '.'}
      </p>

      <div role="tablist" aria-label="Analytics sections" className="grid grid-cols-3 gap-1 rounded-md bg-sunken p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`an-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls="an-panel"
            onClick={() => setTab(t.id)}
            className={`h-8 rounded text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div id="an-panel" role="tabpanel" aria-labelledby={`an-tab-${tab}`} className="flex flex-col gap-6">
        {tab === 'overview' && (
          <>
            <section aria-labelledby="chart-h">
              <h3 id="chart-h" className="mb-2 text-sm font-medium">
                Last 14 days
              </h3>
              <BarChart days={days} />
              {truncated && (
                <p className="mt-2 text-xs text-muted">
                  The chart and the device, OS and browser lists use the latest{' '}
                  {nf.format(data.history.length)} clicks.
                </p>
              )}
            </section>
            <div className="grid gap-6 sm:grid-cols-2">
              <BreakdownList title="Device" rows={devices} />
              <BreakdownList title="Operating system" rows={systems} />
              <BreakdownList title="Browser" rows={browsers} />
            </div>
            <section aria-labelledby="recent-h">
              <h3 id="recent-h" className="mb-2 text-sm font-medium">
                Recent clicks
              </h3>
              <ul className="divide-y divide-line rounded-md border border-line text-sm">
                {recent.map((c, i) => {
                  const t = parseTimestamp(c.timestamp)
                  const where = [c.city, c.countryCode].filter(Boolean).join(', ')
                  return (
                    <li
                      key={`${c.timestamp ?? 'x'}-${i}`}
                      className="flex flex-col gap-0.5 px-3 py-2 sm:flex-row sm:justify-between sm:gap-4"
                    >
                      <span>
                        {c.browser} on {c.os} <span className="text-muted">({c.deviceType})</span>
                      </span>
                      <span className="text-muted">
                        {[c.source ?? 'Direct', where].filter(Boolean).join(' · ')}
                        {t ? ` · ${whenFmt.format(t)}` : ''}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </section>
          </>
        )}

        {tab === 'audience' && (
          <div className="grid gap-6 sm:grid-cols-2">
            <BreakdownList title="Countries" rows={rows(s.countries, (r) => (r.label ? `${r.name} · ${r.label}` : r.name))} />
            <BreakdownList title="Cities" rows={rows(s.cities)} />
            <BreakdownList title="Languages" rows={rows(s.languages)} />
            <p className="text-xs text-muted sm:col-span-2">
              Clicks recorded before location tracking was added show as Unknown. Local and private
              addresses have no location.
            </p>
          </div>
        )}

        {tab === 'sources' && (
          <div className="grid gap-6 sm:grid-cols-2">
            <BreakdownList title="Traffic sources" rows={rows(s.sources)} />
            <BreakdownList title="Campaigns" rows={rows(s.campaigns)} />
            <p className="text-xs text-muted sm:col-span-2">
              Campaigns come from utm_source, utm_medium and utm_campaign (or src and ref) on the short
              link, for example <span className="font-mono">/{data.shortId}?src=newsletter</span>. The tags
              are not passed on to the destination.
            </p>
          </div>
        )}
      </div>
    </>
  )
}

function ExportButtons({ shortId }: { shortId: string }) {
  const [busy, setBusy] = useState<ExportFormat | null>(null)

  async function run(format: ExportFormat) {
    setBusy(format)
    try {
      await downloadClicks(shortId, format)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section aria-labelledby="export-h">
      <h3 id="export-h" className="mb-1 text-sm font-medium">
        Export
      </h3>
      <p className="mb-3 text-sm text-muted">
        Every recorded click for this link, newest first (not just the latest 500), including bot and
        preview hits marked with is_bot. Visitor ids are anonymous and change every day.
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnSecondary} disabled={busy !== null} onClick={() => void run('csv')}>
          <Download size={16} aria-hidden="true" />
          {busy === 'csv' ? 'Exporting...' : 'Export CSV'}
        </button>
        <button type="button" className={btnSecondary} disabled={busy !== null} onClick={() => void run('json')}>
          <Download size={16} aria-hidden="true" />
          {busy === 'json' ? 'Exporting...' : 'Export JSON'}
        </button>
      </div>
    </section>
  )
}
