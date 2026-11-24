import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API_PATHS = [
  '/register', '/token', '/shorten', '/dashboard', '/analytics', '/qrcode', '/links',
  '/api-keys', '/mcp', '/oauth', '/.well-known', '/connected-apps',
]
// Short links (/abc123) are single path segments outside /static/; send them to the backend
// so they redirect in dev exactly as they do in production.
const SHORT_LINK = '^/(?!static(?:/|$)|@)[A-Za-z0-9_-]+/?$'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Optional local dev only: set VITE_PROXY_TARGET (e.g. http://localhost:8000)
  // to forward API calls. Production is same-origin and does not use this.
  const target = loadEnv(mode, process.cwd(), '').VITE_PROXY_TARGET
  return {
    plugins: [react(), tailwindcss()],
    base: '/static/',
    build: {
      outDir: '../static',
      emptyOutDir: true,
    },
    server: target
      ? {
          proxy: Object.fromEntries(
            [...API_PATHS, SHORT_LINK].map((p) => [p, { target, changeOrigin: true, secure: true }]),
          ),
        }
      : undefined,
  }
})
