import { useCallback, useEffect, useId, useState, type FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  createApiKey,
  listApiKeys,
  listConnectedApps,
  revokeApiKey,
  revokeConnectedApp,
  type ApiKey,
  type ConnectedApp,
  type NewApiKey,
} from '../api'
import { btnGhost, btnPrimary, btnSecondary, card, inputClass } from '../lib/ui'
import { CopyButton } from './CopyButton'

const MAX_KEYS = 5
const dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

const TOOLS: [string, string][] = [
  ['list_links', 'Your links with click totals and expiry.'],
  ['link_analytics', 'Clicks per day, unique visitors, devices, countries, sources and campaigns for one link.'],
  ['clicks_by', 'Clicks for one link grouped by country, city, language, source, campaign, device, OS or browser.'],
  ['recent_clicks', 'The latest clicks on a link (up to 500).'],
  ['account_summary', 'Totals, top links, and this week compared with last week.'],
  ['create_short_link', 'Create a short link, with an optional alias and expiry.'],
  ['update_link', 'Change a link\'s destination or expiry.'],
]

const PROMPTS = [
  'Which of my links got the most clicks this week?',
  'Where did the clicks on my newsletter link come from?',
  'Shorten https://example.com/launch with the alias launch.',
]

function when(ts: string | null): string {
  if (!ts) return 'never'
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? 'never' : dateFmt.format(d)
}

function CodeBlock({ text, label }: { text: string; label: string }) {
  return (
    <div className="relative">
      <pre
        tabIndex={0}
        aria-label={label}
        className="overflow-x-auto rounded-md border border-line bg-sunken p-3 pr-12 font-mono text-xs leading-relaxed"
      >
        {text}
      </pre>
      <div className="absolute right-1.5 top-1.5">
        <CopyButton text={text} label={`Copy ${label}`} iconOnly className={`${btnGhost} px-2`} />
      </div>
    </div>
  )
}

function ConnectedApps() {
  const [apps, setApps] = useState<ConnectedApp[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setApps(await listConnectedApps())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load connected apps.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onRevoke(a: ConnectedApp) {
    if (!window.confirm(`Disconnect "${a.name}"? It will lose access to your links right away.`)) return
    try {
      await revokeConnectedApp(a.clientId)
      toast.success('App disconnected')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not disconnect the app.')
    }
  }

  return (
    <div className={card}>
      {error ? (
        <p className="p-4 text-sm text-danger">{error}</p>
      ) : apps === null ? (
        <p className="p-4 text-sm text-muted">Loading connected apps...</p>
      ) : apps.length === 0 ? (
        <p className="p-4 text-sm text-muted">No apps connected yet. Apps you approve with Claude sign-in show up here.</p>
      ) : (
        <ul>
          {apps.map((a) => (
            <li
              key={a.clientId}
              className="flex flex-col gap-2 border-b border-line px-4 py-3 last:border-b-0 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{a.name}</p>
                <p className="text-xs text-muted">
                  connected {when(a.createdAt)} · last used {when(a.lastUsedAt)}
                </p>
              </div>
              <button
                type="button"
                className={btnSecondary}
                onClick={() => void onRevoke(a)}
                aria-label={`Disconnect ${a.name}`}
              >
                Disconnect
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ConnectClaude() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [fresh, setFresh] = useState<NewApiKey | null>(null)
  const uid = useId()

  const load = useCallback(async () => {
    try {
      setKeys(await listApiKeys())
      setLoadError(null)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not load API keys.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const n = name.trim()
    if (!n) {
      setFormError('Give the key a name, for example "Claude Code on my laptop".')
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      setFresh(await createApiKey(n))
      setName('')
      await load()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  async function onRevoke(k: ApiKey) {
    if (!window.confirm(`Revoke "${k.name}"? Anything using this key stops working.`)) return
    try {
      await revokeApiKey(k.id)
      if (fresh?.id === k.id) setFresh(null)
      toast.success('Key revoked')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not revoke the key.')
    }
  }

  const origin = window.location.origin
  const keyText = fresh?.key ?? '<your-api-key>'
  const cliCommand = `claude mcp add --transport http hop ${origin}/mcp --header "Authorization: Bearer ${keyText}"`
  const jsonConfig = JSON.stringify(
    { mcpServers: { hop: { type: 'http', url: `${origin}/mcp`, headers: { Authorization: `Bearer ${keyText}` } } } },
    null,
    2,
  )
  const atLimit = (keys?.length ?? 0) >= MAX_KEYS

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="mcp-h">
        <h2 id="mcp-h" className="text-lg font-semibold">
          Connect to Claude
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          hop runs an MCP server at <span className="font-mono">{origin}/mcp</span>. Connect it and you can
          ask Claude questions about your links in plain language, and have it create or edit links. It only
          sees your own links.
        </p>
      </section>

      <section aria-labelledby="web-h" className="flex flex-col gap-3">
        <h3 id="web-h" className="font-medium">
          Claude on the web, desktop and mobile
        </h3>
        <ol className="max-w-2xl list-decimal space-y-1.5 pl-5 text-sm text-muted">
          <li>In Claude, open Settings, then Connectors, then Add custom connector.</li>
          <li>Paste the URL below.</li>
          <li>Claude sends you to hop. Sign in and press Allow.</li>
        </ol>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <code className="min-w-0 flex-1 break-all rounded-md border border-line bg-sunken px-3 py-2 font-mono text-xs">
            {origin}/mcp
          </code>
          <CopyButton text={`${origin}/mcp`} label="Copy URL" />
        </div>
        <p className="text-sm text-muted">
          Custom connectors may depend on your Claude plan. You can disconnect an app below at any time.
        </p>
        <h4 className="mt-2 text-sm font-medium">Connected apps</h4>
        <ConnectedApps />
      </section>

      <h3 className="-mb-4 font-medium">Claude Code and other MCP clients</h3>
      <p className="-mb-4 max-w-2xl text-sm text-muted">
        These use a personal API key instead of signing in. Keys work with any MCP client that accepts a
        bearer token header.
      </p>

      <section aria-labelledby="keys-h" className="flex flex-col gap-3">
        <h3 id="keys-h" className="font-medium">
          1. Create an API key
        </h3>
        <form onSubmit={onCreate} className={`${card} p-4`} noValidate>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex flex-1 flex-col gap-1.5">
              <label htmlFor={`${uid}-name`} className="text-sm font-medium">
                Key name
              </label>
              <input
                id={`${uid}-name`}
                className={inputClass}
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={50}
                placeholder="Claude Code on my laptop"
                autoComplete="off"
                disabled={atLimit}
              />
            </div>
            <button type="submit" className={`${btnPrimary} h-10`} disabled={busy || atLimit}>
              {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
              Create key
            </button>
          </div>
          <div role="alert" className="mt-2 min-h-5 text-sm text-danger">
            {formError ?? (atLimit ? `You have ${MAX_KEYS} active keys, the maximum. Revoke one to create another.` : '')}
          </div>
        </form>

        {fresh && (
          <div role="status" className="rounded-lg border border-accent bg-accent-soft p-4">
            <p className="text-sm font-medium">Copy your new key now. It is shown only once.</p>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 break-all rounded-md border border-line bg-surface px-3 py-2 font-mono text-xs">
                {fresh.key}
              </code>
              <CopyButton text={fresh.key} label="Copy key" />
            </div>
            <button type="button" className={`${btnGhost} mt-2 -ml-3.5`} onClick={() => setFresh(null)}>
              I have saved it
            </button>
          </div>
        )}

        <div className={card}>
          {loadError ? (
            <p className="p-4 text-sm text-danger">{loadError}</p>
          ) : keys === null ? (
            <p className="p-4 text-sm text-muted">Loading keys...</p>
          ) : keys.length === 0 ? (
            <p className="p-4 text-sm text-muted">No API keys yet. Create one above.</p>
          ) : (
            <ul>
              {keys.map((k) => (
                <li
                  key={k.id}
                  className="flex flex-col gap-2 border-b border-line px-4 py-3 last:border-b-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{k.name}</p>
                    <p className="text-xs text-muted">
                      <span className="font-mono">{k.prefix}...</span> · created {when(k.createdAt)} · last used{' '}
                      {when(k.lastUsedAt)}
                    </p>
                  </div>
                  <button
                    type="button"
                    className={btnSecondary}
                    onClick={() => void onRevoke(k)}
                    aria-label={`Revoke key ${k.name}`}
                  >
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section aria-labelledby="setup-h" className="flex flex-col gap-3">
        <h3 id="setup-h" className="font-medium">
          2. Add hop to your client
        </h3>
        <p className="text-sm text-muted">
          {fresh
            ? 'These snippets include the key you just created.'
            : 'Replace <your-api-key> with a key from above. Snippets fill in automatically right after you create one.'}
        </p>
        <div>
          <p className="mb-1.5 text-sm font-medium">Claude Code</p>
          <CodeBlock text={cliCommand} label="Claude Code command" />
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Other MCP clients</p>
          <p className="mb-1.5 text-sm text-muted">
            For MCP clients that support remote HTTP servers with custom headers. Config field names vary
            by client, so check yours.
          </p>
          <CodeBlock text={jsonConfig} label="MCP JSON config" />
        </div>
      </section>

      <section aria-labelledby="try-h" className="grid gap-6 sm:grid-cols-2">
        <div>
          <h3 id="try-h" className="mb-2 font-medium">
            Things to ask
          </h3>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
            {PROMPTS.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 font-medium">Tools Claude gets</h3>
          <dl className="space-y-1.5 text-sm">
            {TOOLS.map(([n, d]) => (
              <div key={n}>
                <dt className="inline font-mono text-xs">{n}</dt> <dd className="inline text-muted">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  )
}
