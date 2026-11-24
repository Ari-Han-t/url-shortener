import { ExternalLink } from 'lucide-react'
import { shortLink, type ShortenResult } from '../api'
import { describeExpiry } from '../lib/expiry'
import { displayLink } from '../lib/format'
import { btnSecondary, card } from '../lib/ui'
import { CopyButton } from './CopyButton'
import { QrImage } from './QrImage'

export function ResultCard({ result }: { result: ShortenResult }) {
  const link = shortLink(result.shortId)
  return (
    <section aria-label="New short link" className={`${card} flex flex-col gap-5 p-4 sm:flex-row sm:p-5`}>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted">
          {result.alreadyExisted ? 'You already had a link for this URL' : 'Your short link'}
        </p>
        <p className="mt-1 break-all font-mono text-lg font-medium">{displayLink(link)}</p>
        <p className="mt-1 truncate text-sm text-muted" title={result.longUrl}>
          {result.longUrl}
        </p>
        {result.expiresAt && <p className="mt-1 text-sm text-muted">{describeExpiry(result.expiresAt)}</p>}
        <div className="mt-4 flex flex-wrap gap-2">
          <CopyButton text={link} label="Copy link" />
          <a className={btnSecondary} href={link} target="_blank" rel="noreferrer">
            <ExternalLink size={16} aria-hidden="true" />
            Open
          </a>
        </div>
      </div>
      <QrImage key={result.shortId} shortId={result.shortId} size={140} />
    </section>
  )
}
