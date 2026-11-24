import { useState } from 'react'
import { Download } from 'lucide-react'
import { qrUrl } from '../api'
import { btnSecondary } from '../lib/ui'

/** QR image plus download. The image is requested only when this renders (the endpoint is rate limited). */
export function QrImage({ shortId, size = 160 }: { shortId: string; size?: number }) {
  const [failed, setFailed] = useState(false)
  const src = qrUrl(shortId)

  return (
    <div className="flex flex-col items-start gap-3">
      <div
        className="flex items-center justify-center rounded-md border border-line bg-white"
        style={{ width: size, height: size }}
      >
        {failed ? (
          <p className="px-3 text-center text-xs text-muted">
            QR code not available right now. Try again in a minute.
          </p>
        ) : (
          <img
            src={src}
            alt={`QR code for hop link ${shortId}`}
            width={size}
            height={size}
            onError={() => setFailed(true)}
          />
        )}
      </div>
      {!failed && (
        <a className={btnSecondary} href={src} download={`hop-${shortId}.png`}>
          <Download size={16} aria-hidden="true" />
          Download PNG
        </a>
      )}
    </div>
  )
}
