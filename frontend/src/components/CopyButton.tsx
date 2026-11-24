import { useEffect, useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import toast from 'react-hot-toast'
import { copyText } from '../lib/format'
import { btnSecondary } from '../lib/ui'

interface Props {
  text: string
  label?: string
  className?: string
  iconOnly?: boolean
}

export function CopyButton({ text, label = 'Copy', className = btnSecondary, iconOnly }: Props) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  async function onClick() {
    if (await copyText(text)) {
      setCopied(true)
      toast.success('Link copied')
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setCopied(false), 1500)
    } else {
      toast.error('Could not copy. Select the link and copy it manually.')
    }
  }

  const Icon = copied ? Check : Copy
  return (
    <button
      type="button"
      className={className}
      onClick={onClick}
      aria-label={iconOnly ? `${label} ${text}` : undefined}
      title={iconOnly ? label : undefined}
    >
      <Icon size={16} aria-hidden="true" />
      {!iconOnly && (copied ? 'Copied' : label)}
    </button>
  )
}
