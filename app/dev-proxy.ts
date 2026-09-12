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
  '/ambient', '/assistant', '/backup', '/catalog', '/credentials', '/devices', '/discovered',
  '/drafts', '/events', '/flows', '/geo', '/health', '/home', '/location', '/look', '/pair',
  '/phone', '/phones', '/presence', '/qr.svg', '/restore', '/rooms', '/rules', '/say', '/scenes',
  '/setup', '/sounds', '/suggestions', '/update',
  '/docs', '/openapi.json', '/redoc',        // FastAPI's own, handy when the panel is not the thing being debugged
] as const

/** The paths that carry a websocket: the live stream, and a camera's WebRTC signalling. */
export const BRAIN_SOCKETS = ['/stream', '/devices'] as const

export function proxyFor(brain: string) {
  const http = Object.fromEntries(BRAIN_PATHS.map(p => [p, brain]))
  return {
    ...http,
    // A camera's signalling socket lives under /devices too, so that one is both.
    '/devices': { target: brain, ws: true },
    '/stream': { target: brain.replace('http', 'ws'), ws: true },
  }
}
