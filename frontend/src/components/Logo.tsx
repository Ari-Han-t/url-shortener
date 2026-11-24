/** The hop mark: a dot, an arc, and a landing arrow. Same shapes as public/favicon.svg. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <circle cx="8.5" cy="21" r="3" fill="var(--accent-fg)" />
      <path
        d="M8.5 21C8.5 8 23.5 8 23.5 21"
        stroke="var(--accent-fg)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M20 17.8l3.5 3.4 3.5-3.4"
        stroke="var(--accent-fg)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={28} />
      <span className="text-xl font-semibold tracking-tight text-ink">hop</span>
    </span>
  )
}
