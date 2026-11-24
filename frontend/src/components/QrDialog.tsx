import { displayLink } from '../lib/format'
import { shortLink } from '../api'
import { Modal } from './Modal'
import { QrImage } from './QrImage'

interface Props {
  shortId: string | null
  onClose: () => void
}

export function QrDialog({ shortId, onClose }: Props) {
  return (
    <Modal open={shortId !== null} title="QR code" onClose={onClose}>
      {shortId && (
        <div className="flex flex-col gap-3">
          <p className="break-all font-mono text-sm text-muted">{displayLink(shortLink(shortId))}</p>
          <QrImage shortId={shortId} size={220} />
        </div>
      )}
    </Modal>
  )
}
