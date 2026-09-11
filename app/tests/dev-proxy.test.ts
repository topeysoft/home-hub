/* The dev server has to split paths between the brain and the panel the same way production does.
   This list was maintained by hand and had gone stale: nine paths the panel calls fell through to
   Vite, which answered them with index.html, so those screens worked everywhere except in
   `npm run dev`. Nothing said so. This is what says so. */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { BRAIN_PATHS, BRAIN_SOCKETS, proxyFor } from '../dev-proxy'

/** Every path the panel asks the brain for, read out of the code that asks. */
function pathsThePanelCalls(): string[] {
  const files = [...readdirSync('src').filter(f => f.endsWith('.ts') || f.endsWith('.vue')).map(f => `src/${f}`)]
  const found = new Set<string>()
  for (const file of files) {
    const src = readFileSync(file, 'utf8')
    // request('/x'), post('/x'), get(`/x/${id}`), del('/x') — the four ways api.ts reaches the brain
    for (const m of src.matchAll(/\b(?:request|post|get|del)\(\s*[`'"](\/[a-z0-9._-]+)/gi)) found.add(m[1])
    for (const m of src.matchAll(/\bfetch\(\s*[`'"](\/[a-z0-9._-]+)/gi)) found.add(m[1])
  }
  return [...found].sort()
}

const covered = (p: string) => BRAIN_PATHS.some(q => p === q || p.startsWith(q + '/'))

describe('what the dev server sends to the brain', () => {
  it('covers every path the panel actually calls', () => {
    const missing = pathsThePanelCalls().filter(p => !covered(p))
    expect(missing, `these would come back as index.html in npm run dev: ${missing.join(', ')}`).toEqual([])
  })

  it('finds the calls at all, so an empty sweep cannot pass for a clean one', () => {
    const called = pathsThePanelCalls()
    expect(called.length).toBeGreaterThan(10)
    expect(called).toContain('/home')
  })

  it('sends the live stream and camera signalling over a websocket, not as plain http', () => {
    const proxy = proxyFor('http://localhost:8399') as Record<string, any>
    for (const p of BRAIN_SOCKETS) expect(proxy[p]?.ws, p).toBe(true)
    expect(proxy['/stream'].target).toMatch(/^ws:/)
  })

  it('never claims a path Vite needs for itself', () => {
    // Proxying any of these away from Vite breaks hot reload, which is the whole point of the dev server.
    for (const own of ['/@vite', '/@id', '/@fs', '/src', '/node_modules']) {
      expect(covered(own), own).toBe(false)
    }
  })

  it('lists each path once', () => {
    expect(new Set(BRAIN_PATHS).size).toBe(BRAIN_PATHS.length)
  })
})
