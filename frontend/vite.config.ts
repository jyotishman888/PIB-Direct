import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Tunnels (localtunnel / ngrok) serve the app on a hostname Vite doesn't
    // know about, and it rejects unknown Host headers by default.
    allowedHosts: ['.loca.lt', '.ngrok-free.app', '.ngrok.io', '.trycloudflare.com'],
    proxy: {
      // The API is reached through the page's own origin rather than
      // http://127.0.0.1:8000 directly. Two reasons: through a tunnel,
      // 127.0.0.1 would resolve to the *visitor's* machine; and same-origin
      // keeps the session cookie first-party, which sidesteps SameSite and
      // third-party-cookie restrictions entirely.
      //
      // Namespaced under /api because the API and the SPA share path names —
      // `/articles` is both an endpoint and a frontend route — so proxying
      // bare paths would swallow the article detail page.
      //
      // No rewrite: the backend serves /api/... natively, so dev paths are
      // identical to production ones.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
