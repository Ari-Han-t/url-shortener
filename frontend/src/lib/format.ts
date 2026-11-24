export function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

export function displayLink(url: string): string {
  return url.replace(/^https?:\/\//, '')
}

/** Adds https:// when the user typed a bare domain. */
export function normaliseUrl(input: string): string {
  const v = input.trim()
  if (!v) return v
  return /^[a-z][a-z0-9+.-]*:/i.test(v) ? v : `https://${v}`
}

export const nf = new Intl.NumberFormat()

/** The backend sends naive ISO timestamps; treat them as UTC. */
export function parseTimestamp(ts: string | null): Date | null {
  if (!ts) return null
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(ts)
  const d = new Date(hasZone ? ts : `${ts}Z`)
  return Number.isNaN(d.getTime()) ? null : d
}

export function jwtSubject(token: string): string | null {
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    const sub = (JSON.parse(json) as { sub?: unknown }).sub
    return typeof sub === 'string' ? sub : null
  } catch {
    return null
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    document.body.removeChild(ta)
    return ok
  }
}
