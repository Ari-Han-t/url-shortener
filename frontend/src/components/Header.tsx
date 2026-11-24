import { LogOut } from 'lucide-react'
import { btnGhost } from '../lib/ui'
import { Logo } from './Logo'

interface Props {
  username?: string | null
  onSignOut?: () => void
}

export function Header({ username, onSignOut }: Props) {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
        <a href="/" aria-label="hop home" className="rounded-md">
          <Logo />
        </a>
        {onSignOut && (
          <div className="flex items-center gap-2">
            {username && (
              <span className="hidden max-w-[12rem] truncate text-sm text-muted sm:inline">
                {username}
              </span>
            )}
            <button type="button" className={btnGhost} onClick={onSignOut}>
              <LogOut size={16} aria-hidden="true" />
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
