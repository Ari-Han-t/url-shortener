import { useState } from 'react'
import type { LinkItem, ShortenResult } from '../api'
import { useLinks } from '../hooks/useLinks'
import { AnalyticsPanel } from './AnalyticsPanel'
import { ConnectClaude } from './ConnectClaude'
import { DeleteLinkDialog } from './DeleteLinkDialog'
import { EditLinkDialog } from './EditLinkDialog'
import { LinksList } from './LinksList'
import { QrDialog } from './QrDialog'
import { ResultCard } from './ResultCard'
import { ShortenBar } from './ShortenBar'

type Tab = 'links' | 'connect'

const TABS: { id: Tab; label: string }[] = [
  { id: 'links', label: 'Links' },
  { id: 'connect', label: 'Connect to Claude' },
]

export function Dashboard() {
  const { data, loading, error, refresh } = useLinks()
  const [tab, setTab] = useState<Tab>('links')
  const [result, setResult] = useState<ShortenResult | null>(null)
  const [qrFor, setQrFor] = useState<string | null>(null)
  const [statsFor, setStatsFor] = useState<string | null>(null)
  const [editing, setEditing] = useState<LinkItem | null>(null)
  const [deleting, setDeleting] = useState<LinkItem | null>(null)

  function onCreated(r: ShortenResult) {
    setResult(r)
    void refresh()
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6">
      <nav aria-label="Sections" className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            aria-current={tab === t.id ? 'page' : undefined}
            onClick={() => setTab(t.id)}
            className={`-mb-px h-10 border-b-2 px-3 text-sm font-medium transition-colors ${
              tab === t.id
                ? 'border-accent text-ink'
                : 'border-transparent text-muted hover:text-ink'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'links' ? (
        <>
          <ShortenBar onCreated={onCreated} />
          {result && <ResultCard result={result} />}
          <LinksList
            data={data}
            loading={loading}
            error={error}
            onRetry={() => void refresh()}
            onQr={setQrFor}
            onAnalytics={setStatsFor}
            onEdit={setEditing}
            onDelete={setDeleting}
          />
          <QrDialog shortId={qrFor} onClose={() => setQrFor(null)} />
          <AnalyticsPanel shortId={statsFor} onClose={() => setStatsFor(null)} />
          {editing && (
            <EditLinkDialog
              link={editing}
              onClose={() => setEditing(null)}
              onSaved={() => {
                setResult(null)
                void refresh()
              }}
            />
          )}
          {deleting && (
            <DeleteLinkDialog
              link={deleting}
              onClose={() => setDeleting(null)}
              onDeleted={() => {
                setResult((r) => (r?.shortId === deleting.shortId ? null : r))
                void refresh()
              }}
            />
          )}
        </>
      ) : (
        <ConnectClaude />
      )}
    </div>
  )
}
