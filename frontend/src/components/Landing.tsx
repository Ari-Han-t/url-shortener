import type { Auth } from '../hooks/useAuth'
import { AuthCard } from './AuthCard'

const FEATURES = [
  {
    title: 'Aliases and QR codes',
    body: 'Pick your own short ID with letters, numbers, hyphens and underscores, or let hop generate one. Every link has a QR code you can download as a PNG. You can change where a link points later, and set it to expire.',
  },
  {
    title: 'Click analytics',
    body: 'See clicks by device, OS, browser, referrer and time for each link. IP addresses are stored only as SHA-256 hashes, and the page loads no third-party scripts.',
  },
  {
    title: 'Export your data',
    body: 'Download every recorded click for a link as CSV or JSON.',
  },
  {
    title: 'Ask Claude',
    body: 'Connect hop to Claude Code or another MCP client with an API key, then ask in plain language which links did best and where the clicks came from.',
  },
]

const STEPS = [
  'A visitor opens a short link. hop looks the ID up in Redis.',
  'If it is not in Redis, hop reads it from Postgres and caches it for an hour.',
  'The visitor is redirected right away.',
  'The click (device, OS, browser, referrer, hashed IP) is written to Postgres in a background task after the redirect.',
]

const STORED = [
  'Time of the click, and your short ID.',
  'Device type, operating system and browser, read from the user agent. The raw user agent string is not kept.',
  'Country, region and city, looked up offline from the IP address. Nothing finer than city.',
  'Primary browser language, for example en-IN.',
  'Referrer site only (no path or query), a friendly source name such as LinkedIn, and utm_source, utm_medium, utm_campaign (or src, ref) if the short link has them.',
  'An anonymous visitor id: a SHA-256 hash of the IP address, user agent and short ID, mixed with a random salt that changes every day and is deleted after two days.',
  'Whether the visit looks like a bot or link preview. These are kept apart and not counted as clicks.',
]

const NOT_STORED = [
  'No cookies, local storage or tracking scripts on short links.',
  'No raw IP addresses, and no IP hash that works across days.',
  'No fingerprinting, no cross-site tracking, no selling or sharing of click data.',
]

export function Landing({ auth }: { auth: Pick<Auth, 'signIn' | 'signUp'> }) {
  return (
    <>
      <section className="mx-auto grid max-w-5xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1fr_22rem] md:items-start md:py-16">
        <div>
          <h1 className="max-w-lg text-3xl font-semibold tracking-tight sm:text-4xl">
            Short links with click analytics you own, and can ask Claude about.
          </h1>
          <p className="mt-4 max-w-lg text-base text-muted">
            hop is a self-hosted URL shortener. It turns a long URL into a short one, optionally with
            your own alias, and records where the clicks come from. Create an account to start.
          </p>
        </div>
        <AuthCard auth={auth} />
      </section>

      <section aria-labelledby="features" className="border-t border-line">
        <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
          <h2 id="features" className="text-lg font-semibold">
            What it does
          </h2>
          <dl className="mt-6 grid gap-x-8 gap-y-6 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title}>
                <dt className="font-medium">{f.title}</dt>
                <dd className="mt-1 text-sm text-muted">{f.body}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section aria-labelledby="how" className="border-t border-line">
        <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
          <h2 id="how" className="text-lg font-semibold">
            How a redirect works
          </h2>
          <ol className="mt-6 max-w-2xl space-y-3 text-sm">
            {STEPS.map((s, i) => (
              <li key={s} className="flex gap-3">
                <span
                  aria-hidden="true"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent"
                >
                  {i + 1}
                </span>
                <span className="pt-0.5 text-muted">{s}</span>
              </li>
            ))}
          </ol>
          <p className="mt-6 max-w-2xl text-sm text-muted">
            Only http and https destinations are accepted. Sign-in, sign-up and most API endpoints are rate limited per IP address. Each click stores a hash of
            the visitor IP, the browser user agent and the referrer. hop is a single-server project:
            no per-user domains or teams yet.
          </p>
        </div>
      </section>

      <section aria-labelledby="records" className="border-t border-line">
        <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
          <h2 id="records" className="text-lg font-semibold">
            What hop records
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            This is the full list of what is stored for each click on a short link.
          </p>
          <div className="mt-6 grid gap-8 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-medium">Stored</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-muted">
                {STORED.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-medium">Not stored</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-muted">
                {NOT_STORED.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
              <p className="mt-6 text-sm text-muted">
                Because the visitor id changes daily, unique visitors are counted per day. The same
                person on two days counts twice.
              </p>
            </div>
          </div>
          <p className="mt-8 text-xs text-muted">
            IP geolocation by{' '}
            <a className="underline underline-offset-2 hover:text-ink" href="https://db-ip.com" target="_blank" rel="noreferrer">
              DB-IP
            </a>{' '}
            (CC BY 4.0).
          </p>
        </div>
      </section>
    </>
  )
}
