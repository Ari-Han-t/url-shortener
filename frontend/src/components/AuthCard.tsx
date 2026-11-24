import { useId, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import type { Auth } from '../hooks/useAuth'
import { btnPrimary, card, inputClass } from '../lib/ui'

type Mode = 'signin' | 'signup'

const TABS: { id: Mode; label: string }[] = [
  { id: 'signin', label: 'Sign in' },
  { id: 'signup', label: 'Create account' },
]

export function AuthCard({ auth }: { auth: Pick<Auth, 'signIn' | 'signUp'> }) {
  const [mode, setMode] = useState<Mode>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const uid = useId()

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const name = username.trim()
    if (mode === 'signup') {
      if (name.length < 3 || name.length > 50) {
        setError('Username must be 3 to 50 characters.')
        return
      }
      if (password.length < 8) {
        setError('Password must be at least 8 characters.')
        return
      }
    }
    setBusy(true)
    setError(null)
    try {
      if (mode === 'signup') await auth.signUp(name, password)
      else await auth.signIn(name, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  const signup = mode === 'signup'

  return (
    <div className={`${card} p-5 sm:p-6`}>
      <div role="tablist" aria-label="Account" className="mb-5 grid grid-cols-2 gap-1 rounded-md bg-sunken p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`${uid}-tab-${t.id}`}
            aria-selected={mode === t.id}
            aria-controls={`${uid}-panel`}
            tabIndex={mode === t.id ? 0 : -1}
            onClick={() => switchMode(t.id)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                const next = mode === 'signin' ? 'signup' : 'signin'
                switchMode(next)
                document.getElementById(`${uid}-tab-${next}`)?.focus()
              }
            }}
            className={`h-8 rounded text-sm font-medium transition-colors ${
              mode === t.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form
        id={`${uid}-panel`}
        role="tabpanel"
        aria-labelledby={`${uid}-tab-${mode}`}
        onSubmit={onSubmit}
        className="flex flex-col gap-4"
        noValidate
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${uid}-user`} className="text-sm font-medium">
            Username
          </label>
          <input
            id={`${uid}-user`}
            className={inputClass}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${uid}-pass`} className="text-sm font-medium">
            Password
          </label>
          <input
            id={`${uid}-pass`}
            type="password"
            className={inputClass}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={signup ? 'new-password' : 'current-password'}
            aria-describedby={signup ? `${uid}-hint` : undefined}
            required
          />
          {/* Reserved height so switching tabs does not shift the layout. */}
          <p id={`${uid}-hint`} className="h-4 text-xs text-muted">
            {signup ? 'At least 8 characters.' : ''}
          </p>
        </div>

        <div role="alert" className="min-h-5 text-sm text-danger">
          {error}
        </div>

        <button type="submit" className={`${btnPrimary} h-10 w-full`} disabled={busy}>
          {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          {signup ? 'Create account' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
