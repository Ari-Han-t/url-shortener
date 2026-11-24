import { BarChart3, Pencil, QrCode, Trash2 } from 'lucide-react'
import { shortLink, type DashboardData, type LinkItem } from '../api'
import { describeExpiry } from '../lib/expiry'
import { displayLink, nf } from '../lib/format'
import { btnGhost, card } from '../lib/ui'
import { CopyButton } from './CopyButton'

interface Props {
  data: DashboardData | null
  loading: boolean
  error: string | null
  onRetry: () => void
  onQr: (shortId: string) => void
  onAnalytics: (shortId: string) => void
  onEdit: (link: LinkItem) => void
  onDelete: (link: LinkItem) => void
}

export function LinksList({ data, loading, error, onRetry, onQr, onAnalytics, onEdit, onDelete }: Props) {
  return (
    <section aria-labelledby="links-heading">
      <div className="mb-3 flex items-end justify-between gap-4">
        <h2 id="links-heading" className="text-lg font-semibold">
          Your links
        </h2>
        {data && (
          <p className="text-sm text-muted">
            {nf.format(data.links.length)} {data.links.length === 1 ? 'link' : 'links'},{' '}
            {nf.format(data.totalClicks)} {data.totalClicks === 1 ? 'click' : 'clicks'} in total
          </p>
        )}
      </div>

      <div className={card}>
        {loading ? (
          <ul aria-busy="true" aria-label="Loading links">
            {[0, 1, 2].map((i) => (
              <li key={i} className="h-[4.5rem] border-b border-line px-4 py-3 last:border-b-0">
                <div className="h-4 w-40 rounded bg-sunken" />
                <div className="mt-2 h-3 w-64 max-w-full rounded bg-sunken" />
              </li>
            ))}
          </ul>
        ) : error ? (
          <div className="p-6 text-sm">
            <p className="text-danger">{error}</p>
            <button type="button" className={`${btnGhost} mt-3 -ml-3.5`} onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : data && data.links.length === 0 ? (
          <div className="p-6 text-sm text-muted">
            <p className="font-medium text-ink">No links yet.</p>
            <p className="mt-1">Paste a URL above and press Shorten. Your links will show up here.</p>
          </div>
        ) : (
          <ul>
            {data?.links.map((l) => {
              const link = shortLink(l.shortId)
              return (
                <li
                  key={l.shortId}
                  className={`flex flex-col gap-2 border-b border-line px-4 py-3 last:border-b-0 sm:flex-row sm:items-center sm:gap-4 ${l.expired ? 'bg-sunken/60' : ''}`}
                >
                  <div className="min-w-0 flex-1">
                    <a
                      href={link}
                      target="_blank"
                      rel="noreferrer"
                      className={`break-all font-mono text-sm font-medium hover:underline ${l.expired ? 'text-muted line-through' : 'text-accent'}`}
                    >
                      {displayLink(link)}
                    </a>
                    <p className="truncate text-sm text-muted" title={l.longUrl}>
                      {l.longUrl}
                    </p>
                    {l.expiresAt && (
                      <p className="mt-0.5 text-xs">
                        <span
                          className={`inline-block rounded px-1.5 py-0.5 ${
                            l.expired ? 'bg-line font-medium text-ink' : 'bg-accent-soft text-accent'
                          }`}
                        >
                          {l.expired ? 'Expired' : describeExpiry(l.expiresAt)}
                        </span>
                        {l.expired && <span className="ml-2 text-muted">{describeExpiry(l.expiresAt)}</span>}
                      </p>
                    )}
                  </div>
                  <p className="w-24 shrink-0 text-sm tabular-nums sm:text-right">
                    <span className="font-medium">{nf.format(l.clicks)}</span>{' '}
                    <span className="text-muted">{l.clicks === 1 ? 'click' : 'clicks'}</span>
                  </p>
                  <div className="flex shrink-0 gap-1">
                    <CopyButton text={link} label="Copy" iconOnly className={`${btnGhost} px-2.5`} />
                    <button
                      type="button"
                      className={`${btnGhost} px-2.5`}
                      onClick={() => onQr(l.shortId)}
                      aria-label={`QR code for ${l.shortId}`}
                      title="QR code"
                    >
                      <QrCode size={16} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className={`${btnGhost} px-2.5`}
                      onClick={() => onAnalytics(l.shortId)}
                      aria-label={`Analytics for ${l.shortId}`}
                      title="Analytics"
                    >
                      <BarChart3 size={16} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className={`${btnGhost} px-2.5`}
                      onClick={() => onEdit(l)}
                      aria-label={`Edit ${l.shortId}`}
                      title="Edit"
                    >
                      <Pencil size={16} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className={`${btnGhost} px-2.5`}
                      onClick={() => onDelete(l)}
                      aria-label={`Delete ${l.shortId}`}
                      title="Delete"
                    >
                      <Trash2 size={16} aria-hidden="true" />
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
