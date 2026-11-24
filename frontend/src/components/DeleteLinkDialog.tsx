import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { deleteLink, shortLink, type LinkItem } from '../api'
import { nf, displayLink } from '../lib/format'
import { btnBase, btnSecondary } from '../lib/ui'
import { Modal } from './Modal'

interface Props {
  link: LinkItem
  onClose: () => void
  onDeleted: () => void
}

export function DeleteLinkDialog({ link, onClose, onDeleted }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onConfirm() {
    setBusy(true)
    setError(null)
    try {
      await deleteLink(link.shortId)
      toast.success('Link deleted')
      onDeleted()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Modal open title="Delete link" onClose={onClose}>
      <div className="flex flex-col gap-4 text-sm">
        <p className="break-all font-mono text-muted">{displayLink(shortLink(link.shortId))}</p>
        <p>
          This deletes the link and its {nf.format(link.clicks)} recorded {link.clicks === 1 ? 'click' : 'clicks'}.
          Anyone opening the short link or scanning its QR code will get a "not found" page. This cannot
          be undone.
        </p>
        <div role="alert" className="min-h-5 text-danger">
          {error}
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnSecondary} onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={`${btnBase} bg-danger text-bg hover:opacity-90`}
            onClick={() => void onConfirm()}
            disabled={busy}
          >
            {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
            Delete link
          </button>
        </div>
      </div>
    </Modal>
  )
}
