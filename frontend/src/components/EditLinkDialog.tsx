import { useId, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { shortLink, updateLink, type LinkChanges, type LinkItem } from '../api'
import { expiryFromChoice, type ExpiryChoice } from '../lib/expiry'
import { displayLink, normaliseUrl } from '../lib/format'
import { btnPrimary, btnSecondary, inputClass } from '../lib/ui'
import { ExpiryField } from './ExpiryField'
import { Modal } from './Modal'

interface Props {
  link: LinkItem
  onClose: () => void
  onSaved: () => void
}

export function EditLinkDialog({ link, onClose, onSaved }: Props) {
  const [url, setUrl] = useState(link.longUrl)
  const [choice, setChoice] = useState<ExpiryChoice>('keep')
  const [date, setDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const uid = useId()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const changes: LinkChanges = {}
    const nextUrl = normaliseUrl(url)
    if (!nextUrl) {
      setError('Enter a destination URL.')
      return
    }
    if (nextUrl !== link.longUrl) changes.longUrl = nextUrl
    const exp = expiryFromChoice(choice, date)
    if (exp.error) {
      setError(exp.error)
      return
    }
    if (exp.value !== undefined) changes.expiresAt = exp.value
    if (Object.keys(changes).length === 0) {
      onClose()
      return
    }
    setBusy(true)
    setError(null)
    try {
      await updateLink(link.shortId, changes)
      toast.success('Link updated')
      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Modal open title="Edit link" onClose={onClose}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <p className="break-all font-mono text-sm text-muted">{displayLink(shortLink(link.shortId))}</p>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${uid}-url`} className="text-sm font-medium">
            Destination URL
          </label>
          <input
            id={`${uid}-url`}
            className={inputClass}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            inputMode="url"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
          />
        </div>
        <ExpiryField choice={choice} date={date} allowKeep onChange={(c, d) => { setChoice(c); setDate(d) }} />
        <p className="text-xs text-muted">
          The short ID cannot be changed, because links and QR codes that are already out there would
          stop working. Changes apply to new visits right away.
        </p>
        <div role="alert" className="min-h-5 text-sm text-danger">
          {error}
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className={btnPrimary} disabled={busy}>
            {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
            Save changes
          </button>
        </div>
      </form>
    </Modal>
  )
}
