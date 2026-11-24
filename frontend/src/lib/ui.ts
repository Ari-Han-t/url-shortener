// Shared class strings so buttons and inputs look the same everywhere.
export const btnBase =
  'inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium h-9 px-3.5 transition-colors disabled:opacity-60 whitespace-nowrap'

export const btnPrimary = `${btnBase} bg-accent text-accent-fg hover:bg-accent-hover`

export const btnSecondary = `${btnBase} border border-line bg-surface text-ink hover:bg-sunken`

export const btnGhost = `${btnBase} text-muted hover:bg-sunken hover:text-ink`

export const inputClass =
  'block w-full h-10 rounded-md border border-line bg-surface px-3 text-sm text-ink placeholder:text-muted/80 focus-visible:outline-2 focus-visible:outline-accent'

export const card = 'rounded-lg border border-line bg-surface'
