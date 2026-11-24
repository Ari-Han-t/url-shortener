import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { btnGhost } from '../lib/ui'

interface Props {
  open: boolean
  title: string
  onClose: () => void
  /** "drawer" slides in from the right on wide screens; "dialog" is centred. */
  variant?: 'dialog' | 'drawer'
  children: ReactNode
}

/** Thin wrapper over the native <dialog>: focus trap, Escape and inert background come for free. */
export function Modal({ open, title, onClose, variant = 'dialog', children }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  useEffect(() => {
    if (!open) return
    document.documentElement.style.overflow = 'hidden'
    return () => {
      document.documentElement.style.overflow = ''
    }
  }, [open])

  const size =
    variant === 'drawer'
      ? 'ml-auto mr-0 my-0 h-dvh max-h-none w-full max-w-xl rounded-none border-y-0 border-r-0'
      : 'm-auto w-[calc(100%-2rem)] max-w-sm rounded-lg'

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
      className={`${size} border border-line bg-surface p-0 text-ink backdrop:bg-black/50`}
    >
      {open && (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="text-base font-semibold">{title}</h2>
            <button type="button" className={btnGhost} onClick={onClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
        </div>
      )}
    </dialog>
  )
}
