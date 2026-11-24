# hop

A self-hosted URL shortener with click analytics. It was built to practise caching, background work and rate limiting, and it is small enough to read in an afternoon.

Live demo: https://short.13-206-56-146.sslip.io

## What it is for

People and small teams who share links (newsletters, portfolio and job links, campaigns, community posts) and want to know which ones get clicked, without sending their audience's click data to a third-party tracker.

- **The data is yours.** It runs on your own server. Raw IP addresses are never stored, there are no cookies, and the web UI loads no third-party scripts.
- **No lock-in.** Export every click for a link as CSV or JSON.
- **Ask Claude.** Connect hop over MCP and ask questions such as "which link did best this week, and where did the clicks come from?" instead of building dashboards.

## Features

- Short links with optional custom aliases (letters, numbers, `-`, `_`).
- Optional expiry (up to 5 years). Expired links show a 410 page and record no clicks.
- Edit a link's destination or expiry, or delete it with its click history. The alias itself cannot be changed.
- QR code per link (PNG, with download).
- Per-link analytics: clicks per day, unique visitors, device, OS, browser, country and city, language, traffic source, campaign tags, recent clicks.
- Bots and link-preview fetches (Slackbot, Googlebot, curl and similar) still get the redirect but are not counted as clicks; they show as a separate count.
- CSV and JSON export of the full click log.
- Personal API keys and an MCP server for Claude Code and other MCP clients.
- Rejects `javascript:`, `data:` and `file:` URLs (only `http` and `https` are accepted).
- Rate limiting on sign-in, sign-up, shortening, editing, analytics, QR codes, exports and the MCP endpoint.

## Stack

- Backend: FastAPI, psycopg2 connection pool, PyJWT, passlib (bcrypt), slowapi
- Storage: PostgreSQL (users, links, click events, API keys), Redis (redirect cache, MCP rate counters)
- Frontend: React 19, Vite, Tailwind CSS 4, TypeScript (built into `static/` and served by FastAPI)
- MCP: the official Python SDK (`mcp`), Streamable HTTP
- Deployment: Docker Compose with nginx in front

## What hop records

For each click on a short link, hop stores:

- the time and the short ID
- device type, OS and browser (parsed from the user agent; the raw user agent string is not stored)
- country code, country, region and city, looked up offline from the IP address (nothing finer than city; coordinates are never read)
- the first `Accept-Language` tag (language, for example `en`, and locale, for example `en-IN`)
- the referrer reduced to scheme and host, the referrer host, and a friendly source name (LinkedIn, X, Google, Hacker News, or the host itself; `Direct` if there is none)
- `utm_source`, `utm_medium`, `utm_campaign` if present on the short link (`src`, `ref` and `source` count as `utm_source`), trimmed to 100 characters. They are not forwarded to the destination.
- a visitor id: `sha256(daily_salt + ip + user_agent + short_id)`. The salt is 32 random bytes per UTC day in the `daily_salts` table, and salts older than two days are deleted. The id cannot be linked across days or across links, and the IP cannot be recovered from it.
- `is_bot`, set from a list of crawler, link-preview and HTTP-library user agents. Bot hits get no visitor id or location, and are excluded from click counts and analytics.

Not stored: raw IP addresses, cookies or local-storage identifiers, fingerprints, or anything sent to a third party. Because visitor ids change daily, "unique visitors" means unique per day; the same person on two days counts twice.

Clicks recorded before these fields existed keep their old values: `ip_address` holds an old unsalted hash for those rows and the new columns are empty. New rows leave `ip_address` and `user_agent` empty. The legal basis and notices for your own audience are your responsibility; this design avoids cookies and personal identifiers so consent banners are generally not needed, but check the rules where you operate.

### Location data

City lookup uses the free DB-IP "IP to City Lite" database, licensed CC BY 4.0. IP geolocation by [DB-IP](https://db-ip.com). The file is opened memory-mapped from `GEOIP_DB_PATH` (default `data/dbip-city-lite.mmdb`). If it is missing, location fields are simply empty. Download or refresh it (it updates monthly) with:

```bash
bash scripts/update_geoip.sh
```

The `data/*.mmdb` file is not committed. The Compose file mounts `./data` into the web container.

## How a redirect works

1. A request for `/{short_id}` arrives. The app looks the ID up in Redis.
2. On a miss it reads the URL from Postgres and caches it in Redis for one hour.
3. The client is redirected (HTTP 307) straight away. The cache lifetime is the shorter of one hour and the time left before the link expires. An expired link gets a 410 page instead, and unknown IDs get a 404 page.
4. The click is written to Postgres by a FastAPI background task after the response is sent. The request handler only copies a few headers and the query string; hashing, location lookup and the insert happen in the task, so recording a click does not add to redirect latency.

## Run it

```bash
cp .env.example .env     # set POSTGRES_*, SECRET_KEY, PUBLIC_BASE_URL
docker compose up -d --build
```

The UI is at http://localhost/ and the interactive API docs at http://localhost/docs. `PUBLIC_BASE_URL` (for example `https://short.example.com`) is the public origin the MCP tools put in the `short_url` they return.

Frontend development:

```bash
cd frontend
npm install
VITE_PROXY_TARGET=http://localhost:8000 npm run dev   # proxies API calls to a running backend
npm run build                                          # writes ../static
```

Tests (pure logic and MCP wiring, no database needed):

```bash
pip install -r requirements.txt pytest httpx
python -m pytest tests
```

## API

JSON in and out. Errors come back as `{"success": false, "message": "..."}` with a 4xx status; rate limits return 429. "Bearer" means a JWT from `POST /token` (valid for 30 minutes).

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/register` | none | `{username (3-50), password (min 8)}`. 5/min. |
| POST | `/token` | none | Form-encoded `username`, `password`. Returns `access_token`. 10/min. |
| POST | `/shorten` | Bearer | `{long_url, custom_id?, expires_at? \| expires_in_days?}`. 20/min. |
| GET | `/dashboard` | Bearer | Your links with clicks, `created_at`, `expires_at`, `updated_at`, `expired`. |
| PATCH | `/links/{short_id}` | Bearer | `{long_url?, expires_at?}`; `expires_at: null` removes the expiry. Owner only. Clears the cached redirect. 30/min. |
| POST | `/links/{short_id}/update` | Bearer | Same as PATCH (nginx only forwards GET, POST, HEAD). |
| DELETE | `/links/{short_id}` | Bearer | Deletes the link and its click events. |
| POST | `/links/{short_id}/delete` | Bearer | Same as DELETE. |
| GET | `/analytics/{short_id}` | Bearer | Totals and the latest 500 clicks. 20/min. |
| GET | `/analytics/{short_id}/export?format=csv\|json` | Bearer | Every click, newest first, as a download. 10/min. |
| GET | `/qrcode/{short_id}` | none | PNG. 10/min. |
| GET | `/{short_id}` | none | 307 redirect. |
| POST | `/api-keys` | Bearer | `{name}`. Returns the full key once. Max 5 active keys. 10/min. |
| GET | `/api-keys` | Bearer | Active keys (name, prefix, last used). No secrets. |
| POST | `/api-keys/{id}/revoke` | Bearer | Revoke a key. `DELETE /api-keys/{id}` does the same. |
| POST | `/mcp` | API key or OAuth token | MCP endpoint (see below). 60 requests/min per key or grant. |
| GET | `/connected-apps` | Bearer | Apps you have approved through OAuth. |
| POST | `/connected-apps/{client_id}/revoke` | Bearer | Disconnect an app. |
| GET | `/.well-known/oauth-protected-resource[/mcp]` | none | RFC 9728 metadata for `/mcp`. |
| GET | `/.well-known/oauth-authorization-server[/oauth]` | none | RFC 8414 metadata for the OAuth server. |
| GET, POST | `/oauth/authorize`, `/oauth/consent`, `/oauth/token`, `/oauth/register`, `/oauth/revoke` | OAuth | The authorization server (see below). |
| GET | `/health` | none | Health check. |

### Export format

Columns: `timestamp` (ISO 8601, UTC), `device_type`, `os`, `browser`, `referer`, `visitor_id`, `country_code`, `country`, `region`, `city`, `language`, `is_bot`, `utm_source`, `utm_medium`, `utm_campaign`, `referrer_host`, `referrer_source`. The export includes bot hits (`is_bot` true); the analytics view does not. `visitor_id` is empty for clicks recorded before it existed. CSV cells that start with `=`, `+`, `-` or `@` are prefixed with `'` so spreadsheets do not run them as formulas.

## Claude and MCP

hop serves an MCP server at `/mcp` (Streamable HTTP, stateless, JSON responses). There are two ways to sign in, and both see only your own links.

**Claude on the web, desktop and mobile (OAuth).** In Claude open Settings, then Connectors, then Add custom connector, and paste `https://your-host/mcp`. Claude sends you to hop; sign in and press Allow. You can disconnect the app later under **Connect to Claude** in hop. (Which Claude plans offer custom connectors is up to Anthropic.)

**Claude Code and other MCP clients (API key).** Create an API key in the web UI under **Connect to Claude**, then:

```bash
claude mcp add --transport http hop https://your-host/mcp --header "Authorization: Bearer hop_..."
```

Other MCP clients that support remote HTTP servers with custom headers can use:

```json
{"mcpServers": {"hop": {"type": "http", "url": "https://your-host/mcp", "headers": {"Authorization": "Bearer hop_..."}}}}
```

Keys look like `hop_...`. Only a SHA-256 hash is stored, so a lost key cannot be shown again; revoke it and create another. Every tool sees only the links of the key's owner.

| Tool | What it does |
| --- | --- |
| `list_links` | Your links with click totals, creation time and expiry. |
| `link_analytics(short_id, days=30)` | Clicks per day, unique visitors, bot hits, and top devices, OS, browsers, countries, cities, languages, sources and campaigns. |
| `clicks_by(short_id, dimension, days=30)` | Clicks grouped by `country`, `city`, `language`, `source`, `campaign`, `device`, `os` or `browser`. |
| `recent_clicks(short_id, limit=50)` | Latest human clicks, newest first (max 500), with city-level location and source. |
| `account_summary` | Link and click totals, top 5 links, last 7 days vs the previous 7, and 30-day unique visitors, top countries, sources and campaigns. |
| `create_short_link(long_url, custom_alias?, expires_in_days?)` | Same validation as `POST /shorten`. |
| `update_link(short_id, long_url?, expires_in_days?, remove_expiry?)` | Change the destination or expiry. The short ID cannot change. |

### OAuth

hop is its own OAuth 2.1 authorization server for `/mcp`, built on the `mcp` SDK's auth handlers (1.30) with Postgres storage. It lives under `/oauth` so hop's own `POST /register` (sign-up) and `POST /token` (login) are unchanged.

- Discovery: an unauthenticated request to `/mcp` gets `401` with `WWW-Authenticate: Bearer resource_metadata="https://your-host/.well-known/oauth-protected-resource/mcp"`. That document (RFC 9728) names the issuer `https://your-host/oauth`, whose metadata (RFC 8414) is served at `/.well-known/oauth-authorization-server/oauth` and at `/.well-known/oauth-authorization-server`.
- Clients register themselves with Dynamic Client Registration (RFC 7591) at `/oauth/register`, including public clients (`token_endpoint_auth_method: none`). Redirect URIs must be `https`, or `http` on `localhost` / `127.0.0.1` / `[::1]`; they are stored in Postgres. Client ID Metadata Documents are not supported by SDK 1.30.
- Authorization code flow with PKCE `S256` only. Codes are single use, expire after 60 seconds, and are bound to the client, redirect URI, code challenge and `resource`. A failed token attempt also consumes the code. `resource` (RFC 8707), if sent, must be the `/mcp` URL.
- `/oauth/authorize` sends you to a hop sign-in page (same password check and 10/min limit as `POST /token`), then a consent page naming the app and where you will be sent back. Forms carry CSRF tokens signed with `SECRET_KEY`, and the short-lived sign-in cookie is `HttpOnly`, `SameSite=Lax` and scoped to `/oauth`. Only registered redirect URIs are ever redirected to.
- Access tokens last 1 hour and refresh tokens 30 days. Refresh tokens rotate on every use; presenting an old one revokes the whole chain. Only SHA-256 hashes of codes and tokens are stored. `POST /oauth/revoke` (RFC 7009) and **Connected apps** in the web UI revoke access.
- There is a single scope, `mcp`, covering reading analytics and creating and editing links.

An API key (`hop_...`) keeps working alongside OAuth tokens. `tests/e2e_oauth.py` runs the whole flow against a running server (`HOP_E2E_URL=http://127.0.0.1:8001 python tests/e2e_oauth.py`).

## Limitations

- One server: one app container, one Postgres, one Redis. Nothing is replicated.
- No custom domain per user, no teams or shared workspaces.
- Link aliases cannot be changed (printed links and QR codes would break). There is no soft delete or undo.
- The analytics charts use the latest 500 clicks per link (the export and MCP `link_analytics` are not limited to 500).
- Cached redirects can be up to an hour stale if a link were changed directly in the database.
- Access tokens last 30 minutes and are kept in `localStorage`; there are no refresh tokens or password reset.
- Rate limits and geolocation use the first `X-Forwarded-For` entry. Run hop behind a proxy that overwrites that header, or clients can spoof their location and rate-limit identity.
- Geolocation is approximate (database accuracy varies, VPN users show their exit city), and bot detection is a user-agent list, so unknown bots are counted as people.
- The bundled nginx forwards only GET, POST and HEAD, which is why keys are revoked with `POST`.
- No licence file is included in this repository.

## Credits

IP geolocation by [DB-IP](https://db-ip.com) (IP to City Lite, CC BY 4.0).

## Source

https://github.com/Ari-Han-t/url-shortener. Built by [Arihant Gupta](https://github.com/Ari-Han-t).
