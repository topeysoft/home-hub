// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Which paths belong to the brain rather than to the panel.
 *
 * In production the brain owns every one of these and serves the panel on whatever is left. The dev
 * server has to reproduce that split, and the list used to be maintained by hand and had gone stale:
 * /health, /phones, /presence, /sounds and five others fell through to Vite, which answered them with
 * index.html, so those screens quietly broke in `npm run dev` and nowhere else. That is the kind of
 * thing that teaches you to stop using the dev server.
 *
 * tests/dev-proxy.test.ts holds this list to every path the panel actually calls, so it cannot rot
 * again without something saying so.
 */
export const BRAIN_PATHS = [
  '/accounts', '/ambient', '/assistant', '/backup', '/bridge', '/catalog', '/credentials', '/devices', '/discovered',
  '/drafts', '/events', '/flows', '/geo', '/happened', '/health', '/home', '/language', '/location', '/look', '/network', '/pair',
  '/phone', '/phones', '/presence', '/qr.svg', '/restart', '/restore', '/rooms', '/rules', '/say', '/scenes',
  '/setup', '/share', '/sounds', '/strip', '/suggestions', '/things', '/update',
  '/docs', '/openapi.json', '/redoc',        // FastAPI's own, handy when the panel is not the thing being debugged
] as const

/** The paths that carry a websocket: the live stream, and a camera's WebRTC signaling. */
export const BRAIN_SOCKETS = ['/stream', '/devices'] as const

/* `changeOrigin` puts the brain's own name in the Host header, in place of the localhost:5173 the
   browser typed. Against a brain on this machine it changes nothing -- uvicorn never reads it -- but
   `tools/dev.sh live` points this at a real house, and a real house has caddy in front of the brain
   picking the site by Host. Without this, every request through the front door is a site caddy does
   not serve. */
export function proxyFor(brain: string) {
  const http = Object.fromEntries(BRAIN_PATHS.map(p => [p, { target: brain, changeOrigin: true }]))
  return {
    ...http,
    // A camera's signaling socket lives under /devices too, so that one is both.
    '/devices': { target: brain, ws: true, changeOrigin: true },
    '/stream': { target: brain.replace('http', 'ws'), ws: true, changeOrigin: true },
  }
}
