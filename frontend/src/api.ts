const TOKEN_KEY = 'hop.token'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface LinkItem {
  shortId: string
  longUrl: string
  clicks: number
  createdAt: string | null
  expiresAt: string | null
  updatedAt: string | null
  expired: boolean
}

export interface DashboardData {
  totalClicks: number
  links: LinkItem[]
}

export interface ClickEvent {
  timestamp: string | null
  deviceType: string
  os: string
  browser: string
  referer: string
  countryCode: string | null
  city: string | null
  source: string | null
  language: string | null
}

export interface CountRow {
  name: string
  label?: string
  clicks: number
}

export interface AnalyticsSummary {
  uniqueVisitors: number
  botHits: number
  countries: CountRow[]
  cities: CountRow[]
  languages: CountRow[]
  sources: CountRow[]
  campaigns: CountRow[]
}

export interface AnalyticsData {
  shortId: string
  longUrl: string
  totalClicks: number
  history: ClickEvent[]
  summary: AnalyticsSummary
}

export interface ShortenResult {
  shortId: string
  longUrl: string
  alreadyExisted: boolean
  expiresAt: string | null
}

// Token storage. localStorage can throw (private mode, blocked storage).
export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function storeToken(value: string | null): void {
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Storage unavailable: the session just will not survive a reload.
  }
}

let token: string | null = getStoredToken()
let onUnauthorized: (() => void) | null = null

export function setToken(next: string | null): void {
  token = next
  storeToken(next)
}

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn
}

export const RATE_LIMIT_MESSAGE = 'Too many attempts. Wait a minute and try again.'

// The backend returns { success: false, message } for errors; FastAPI's
// default shape is { detail }. Accept both.
function messageFrom(body: unknown, status: number): string {
  if (status === 429) return RATE_LIMIT_MESSAGE
  if (body && typeof body === 'object') {
    const b = body as { message?: unknown; detail?: unknown }
    if (typeof b.message === 'string' && b.message) return b.message
    if (typeof b.detail === 'string' && b.detail) return b.detail
  }
  if (status >= 500) return 'The server had a problem. Try again in a moment.'
  return `Request failed (${status}).`
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  json?: unknown
  form?: Record<string, string>
  auth?: boolean
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  } else if (opts.form) {
    body = new URLSearchParams(opts.form)
  }
  const sentToken = opts.auth ? token : null
  if (opts.auth) {
    if (!sentToken) throw new ApiError(401, 'Please sign in.')
    headers.Authorization = `Bearer ${sentToken}`
  }

  let res: Response
  try {
    res = await fetch(path, { method: opts.method ?? 'GET', headers, body })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection.')
  }

  if (!res.ok) {
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      // Non-JSON body, for example a proxy error page.
    }
    // Only treat 401 as an expired session if it was for the token we still hold.
    if (res.status === 401 && sentToken && sentToken === token) {
      onUnauthorized?.()
    }
    throw new ApiError(res.status, messageFrom(data, res.status))
  }
  return res
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts)
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiError(res.status, 'The server sent an unreadable response.')
  }
}

export async function register(username: string, password: string): Promise<void> {
  await request('/register', { method: 'POST', json: { username, password } })
}

export async function login(username: string, password: string): Promise<string> {
  const res = await request<{ access_token: string }>('/token', {
    method: 'POST',
    form: { username, password },
  })
  return res.access_token
}

export async function shorten(
  longUrl: string,
  customId?: string,
  expiresAt?: string,
): Promise<ShortenResult> {
  const res = await request<{
    data: { 'Long Url': string; Short_ID: string; expires_at?: string | null }
    message?: string
  }>('/shorten', {
    method: 'POST',
    auth: true,
    json: {
      long_url: longUrl,
      ...(customId ? { custom_id: customId } : {}),
      ...(expiresAt ? { expires_at: expiresAt } : {}),
    },
  })
  return {
    shortId: res.data.Short_ID,
    longUrl: res.data['Long Url'],
    alreadyExisted: res.message === 'Already existed!',
    expiresAt: res.data.expires_at ?? null,
  }
}

export interface LinkChanges {
  longUrl?: string
  /** ISO time to set, null to remove the expiry, undefined to leave it as is. */
  expiresAt?: string | null
}

// POST rather than PATCH/DELETE: the bundled nginx only forwards GET, POST and HEAD.
export async function updateLink(shortId: string, changes: LinkChanges): Promise<void> {
  const json: Record<string, unknown> = {}
  if (changes.longUrl !== undefined) json.long_url = changes.longUrl
  if (changes.expiresAt !== undefined) json.expires_at = changes.expiresAt
  await request(`/links/${encodeURIComponent(shortId)}/update`, { method: 'POST', auth: true, json })
}

export async function deleteLink(shortId: string): Promise<void> {
  await request(`/links/${encodeURIComponent(shortId)}/delete`, { method: 'POST', auth: true })
}

export async function getDashboard(): Promise<DashboardData> {
  const res = await request<{
    data: {
      'Total Network Clicks': number
      Dashboard: {
        'Short ID': string
        'Long URL': string
        'Total Clicks': number
        created_at?: string | null
        expires_at?: string | null
        updated_at?: string | null
        expired?: boolean
      }[]
    }
  }>('/dashboard', { auth: true })
  return {
    totalClicks: res.data['Total Network Clicks'],
    links: res.data.Dashboard.map((l) => ({
      shortId: l['Short ID'],
      longUrl: l['Long URL'],
      clicks: l['Total Clicks'],
      createdAt: l.created_at ?? null,
      expiresAt: l.expires_at ?? null,
      updatedAt: l.updated_at ?? null,
      expired: l.expired ?? false,
    })),
  }
}

interface SummaryWire {
  unique_visitors: number
  bot_hits: number
  countries: CountRow[]
  cities: CountRow[]
  languages: CountRow[]
  sources: CountRow[]
  campaigns: CountRow[]
}

export async function getAnalytics(shortId: string): Promise<AnalyticsData> {
  const res = await request<{
    data: {
      'Short ID': string
      'Long URL': string
      'Total Clicks': number
      History: {
        timestamp: string | null
        device_type: string
        os: string
        browser: string
        referer: string
        country_code?: string | null
        city?: string | null
        source?: string | null
        language?: string | null
      }[]
      Summary?: SummaryWire
    }
  }>(`/analytics/${encodeURIComponent(shortId)}`, { auth: true })
  const d = res.data
  const sm = d.Summary
  return {
    shortId: d['Short ID'],
    longUrl: d['Long URL'],
    totalClicks: d['Total Clicks'],
    history: d.History.map((h) => ({
      timestamp: h.timestamp,
      deviceType: h.device_type,
      os: h.os,
      browser: h.browser,
      referer: h.referer,
      countryCode: h.country_code ?? null,
      city: h.city ?? null,
      source: h.source ?? null,
      language: h.language ?? null,
    })),
    summary: {
      uniqueVisitors: sm?.unique_visitors ?? 0,
      botHits: sm?.bot_hits ?? 0,
      countries: sm?.countries ?? [],
      cities: sm?.cities ?? [],
      languages: sm?.languages ?? [],
      sources: sm?.sources ?? [],
      campaigns: sm?.campaigns ?? [],
    },
  }
}

export type ExportFormat = 'csv' | 'json'

/** Downloads every recorded click for a link as a file. */
export async function downloadClicks(shortId: string, format: ExportFormat): Promise<void> {
  const res = await send(`/analytics/${encodeURIComponent(shortId)}/export?format=${format}`, {
    auth: true,
  })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `hop-${shortId}-clicks.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export interface ApiKey {
  id: number
  name: string
  prefix: string
  createdAt: string
  lastUsedAt: string | null
}

export interface NewApiKey extends ApiKey {
  key: string
}

interface ApiKeyWire {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at?: string | null
}

const toApiKey = (k: ApiKeyWire): ApiKey => ({
  id: k.id,
  name: k.name,
  prefix: k.prefix,
  createdAt: k.created_at,
  lastUsedAt: k.last_used_at ?? null,
})

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await request<{ data: ApiKeyWire[] }>('/api-keys', { auth: true })
  return res.data.map(toApiKey)
}

export async function createApiKey(name: string): Promise<NewApiKey> {
  const res = await request<{ data: ApiKeyWire & { key: string } }>('/api-keys', {
    method: 'POST',
    auth: true,
    json: { name },
  })
  return { ...toApiKey(res.data), key: res.data.key }
}

// POST rather than DELETE: the bundled nginx only forwards GET, POST and HEAD.
export async function revokeApiKey(id: number): Promise<void> {
  await request(`/api-keys/${id}/revoke`, { method: 'POST', auth: true })
}

export interface ConnectedApp {
  clientId: string
  name: string
  createdAt: string | null
  lastUsedAt: string | null
}

export async function listConnectedApps(): Promise<ConnectedApp[]> {
  const res = await request<{
    data: { client_id: string; client_name: string; created_at: string | null; last_used_at: string | null }[]
  }>('/connected-apps', { auth: true })
  return res.data.map((a) => ({
    clientId: a.client_id,
    name: a.client_name,
    createdAt: a.created_at,
    lastUsedAt: a.last_used_at,
  }))
}

export async function revokeConnectedApp(clientId: string): Promise<void> {
  await request(`/connected-apps/${encodeURIComponent(clientId)}/revoke`, { method: 'POST', auth: true })
}

export const shortLink = (shortId: string): string => `${window.location.origin}/${shortId}`
export const qrUrl = (shortId: string): string => `/qrcode/${encodeURIComponent(shortId)}`
