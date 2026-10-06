// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from 'vitest'
import { addLink, codeOf, houseToOpen, iphoneSafari, labelOf, nearby, originOf } from '../houses/src/houses'

/* The Houses app's rules, pinned to design/houses/ (B, and The app). */

describe('the code', () => {
  it('is what a person typed, without how they read it aloud', () => {
    expect(codeOf('k7q4 - mpwr')).toBe('K7Q4MPWR')
  })
  it('arrives with the house in the fragment, and only a whole one counts', () => {
    expect(addLink('#h=maple-court&c=K7Q4MPWR')).toEqual({ house: 'maple-court', code: 'K7Q4MPWR' })
    expect(addLink('#h=maple-court&c=K7Q4')).toBeNull()
    expect(addLink('#h=Main%20Palace!&c=K7Q4MPWR')).toBeNull()
    expect(addLink('')).toBeNull()
  })
})

describe('where a house is', () => {
  it('is its own name in the app\'s zone, and the mock on a developer\'s machine', () => {
    expect(originOf('temi', { hostname: 'houses.elyir.app', protocol: 'https:' })).toBe('https://temi.elyir.app')
    expect(originOf('temi', { hostname: 'localhost', protocol: 'http:' })).toBe('http://localhost:8399')
    expect(labelOf('https://Temi.elyir.app/')).toBe('temi')
    expect(labelOf('temi.elyir.app')).toBe('temi')
  })
})

describe('which house opens (B, where you are)', () => {
  it('is the one whose Wi-Fi this phone is on', () => {
    expect(houseToOpen([{ id: 'a', reach: 'away', opened: 9 }, { id: 'b', reach: 'here', opened: 1 }])).toBe('b')
  })
  it('else the one opened last', () => {
    expect(houseToOpen([{ id: 'a', reach: 'away', opened: 9 }, { id: 'b', reach: 'offline', opened: 1 }])).toBe('a')
    expect(houseToOpen([])).toBeNull()
  })
})

describe('Safari on an iPhone', () => {
  it('adds nothing, because the Home Screen app keeps its own storage', () => {
    const ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X)'
    expect(iphoneSafari(ua, false)).toBe(true)
    expect(iphoneSafari(ua, true)).toBe(false)
    expect(iphoneSafari('Mozilla/5.0 (Linux; Android 15)', false)).toBe(false)
  })
})

describe('the houses on this Wi-Fi', () => {
  afterEach(() => vi.unstubAllGlobals())

  /* What the maker's own Wi-Fi said on 3 October: one house, three printers, all with names on the relay. */
  const answers: Record<string, () => Response> = {
    'https://nearby.elyir.app/nearby': () => Response.json({ names: ['c3po', 'maple-court', 'obi1', 'r2d2'] }),
    'https://maple-court.elyir.app/alive': () => Response.json({ ok: true, version: 'main-1a2b3c4', commit: '1a2b3c4' }),
    'https://obi1.elyir.app/alive': () => new Response('<!doctype html>', { headers: { 'content-type': 'text/html' } }),
    'https://r2d2.elyir.app/alive': () => new Response('{"detail":"Not Found"}', { status: 404, headers: { 'content-type': 'application/json' } }),
  }

  it('are the names that answer like a hub, and never a printer', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const a = answers[url]
      if (!a) throw new TypeError('Failed to fetch')          // c3po: refused across origins, as a printer is
      return a()
    })
    expect(await nearby({ hostname: 'houses.elyir.app' })).toEqual(['maple-court'])
  })
})
