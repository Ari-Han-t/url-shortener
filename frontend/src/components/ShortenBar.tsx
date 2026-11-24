import { useId, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { shorten, type ShortenResult } from '../api'
import { expiryFromChoice, type ExpiryChoice } from '../lib/expiry'
import { normaliseUrl } from '../lib/format'
import { btnPrimary, card, inputClass } from '../lib/ui'
import { ExpiryField } from './ExpiryField'

const ALIAS_PATTERN = /^[a-zA-Z0-9_-]+$/

export function ShortenBar({ onCreated }: { onCreated: (r: ShortenResult) => void }) {
  const [url, setUrl] = useState('')
  const [alias, setAlias] = useState('')
  const [expiry, setExpiry] = useState<ExpiryChoice>('never')
  const [expiryDate, setExpiryDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const uid = useId()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const longUrl = normaliseUrl(url)
    const customId = alias.trim()
    if (!longUrl) {
      setError('Enter a URL to shorten.')
      return
    }
    if (customId && !ALIAS_PATTERN.test(customId)) {
      setError('Alias can only use letters, numbers, hyphens and underscores.')
      return
    }
    const exp = expiryFromChoice(expiry, expiryDate)
    if (exp.error) {
      setError(exp.error)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await shorten(longUrl, customId || undefined, exp.value ?? undefined)
      onCreated(result)
      if (result.alreadyExisted) toast('You already shortened this URL.')
      setUrl('')
      setAlias('')
      setExpiry('never')
      setExpiryDate('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className={`${card} p-4 sm:p-5`} noValidate>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_11rem_11rem_auto] sm:items-start">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${uid}-url`} className="text-sm font-medium">
            Long URL
          </label>
          <input
            id={`${uid}-url`}
            className={inputClass}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/a/long/path"
            inputMode="url"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${uid}-alias`} className="text-sm font-medium">
            Custom alias <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id={`${uid}-alias`}
            className={inputClass}
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            placeholder="my-link"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
          />
        </div>
        <ExpiryField
          choice={expiry}
          date={expiryDate}
          onChange={(c, d) => {
            setExpiry(c)
            setExpiryDate(d)
          }}
        />
        <button type="submit" className={`${btnPrimary} h-10 sm:mt-[1.625rem] lg:w-28`} disabled={busy}>
          {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          Shorten
        </button>
      </div>
      <div role="alert" className="mt-2 min-h-5 text-sm text-danger">
        {error}
      </div>
    </form>
  )
}
