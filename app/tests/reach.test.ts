// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A screen that can't reach the hub says so (design/out-of-reach/, C, decided 9 October 2026). These pin
   the board: two misses before the band, a tap that never arrived counting as one, no guess while cut
   off, the card's own sentence, and the words. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Device, Room } from '../src/api'
import { forgetDone, perform, store } from '../src/store'
import { bandFor, linkWord, MISSES, missed, probe, reach, reached, stillLine } from '../src/reach'

const room = (devices: Device[]): Room =>
  ({ id: 'kitchen', name: 'Kitchen', devices, intent: 'unknown', set_by: null, hold_until: null })
const light = (state = 'on'): Device => ({ id: 'uc', name: 'Under Cabinet', room_id: 'kitchen', capability: 'light', state, attrs: {} })
const unreachable = () => Promise.reject(new TypeError('Failed to fetch'))
const answering = () => Promise.resolve({ ok: true, status: 200 } as Response)

beforeEach(() => { reached(); reach.heard = null; store.loaded = true; store.toast = null; forgetDone(true) })
afterEach(() => { vi.unstubAllGlobals(); reached() })

describe('noticing', () => {
  it('takes two misses in a row, so one blip raises nothing', () => {
    expect(MISSES).toBe(2)
    missed(1000)
    expect(reach.out).toBe(false)
    missed(31000)
    expect(reach.out).toBe(true)
    expect(reach.since).toBe(1000)
  })

  it('is over the moment a request gets through', async () => {
    missed(); missed()
    await probe(answering)
    expect(reach).toMatchObject({ out: false, misses: 0, since: null })
  })

  it('counts any answer from the hub, and a 5xx as the relay standing in for it', async () => {
    await probe(() => Promise.resolve({ ok: false, status: 404 } as Response))
    expect(reach.misses).toBe(0)
    await probe(() => Promise.resolve({ ok: false, status: 502 } as Response))
    expect(reach.misses).toBe(1)
  })
})

describe('a tap', () => {
  it('that never reached the hub is not blamed on the light: the card says it, and the hub is asked again at once', async () => {
    vi.stubGlobal('fetch', unreachable)
    store.rooms = [room([light()])]
    const d = store.rooms[0].devices[0]
    expect(await perform(d, 'off', undefined, { state: 'off' })).toBe(false)
    expect(d.state).toBe('on')
    expect(store.toast).toBeNull()
    expect(reach.unreached.uc).toBeTypeOf('number')
    await vi.waitFor(() => expect(reach.out).toBe(true))   // the tap's miss, then the probe's
  })

  it('while cut off guesses nothing, so the card never flips and flips back', async () => {
    missed(); missed()
    let seen = ''
    vi.stubGlobal('fetch', () => { seen = d.state; return unreachable() })
    store.rooms = [room([light()])]
    const d = store.rooms[0].devices[0]
    await perform(d, 'off', undefined, { state: 'off' })
    expect(seen).toBe('on')
    expect(store.pending.uc).toBeUndefined()
  })

  it('that gets through while cut off ends it', async () => {
    missed(); missed()
    vi.stubGlobal('fetch', answering)
    store.rooms = [room([light()])]
    expect(await perform(store.rooms[0].devices[0], 'off', undefined, { state: 'off' })).toBe(true)
    expect(reach.out).toBe(false)
  })

  it('that the hub answered with a failure still names the light, because then it is the light', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve({ ok: false, status: 500, json: async () => ({ detail: 'x' }), clone() { return this } } as unknown as Response))
    store.rooms = [room([light()])]
    await perform(store.rooms[0].devices[0], 'off', undefined, { state: 'off' })
    expect(store.toast?.text).toBe('Under Cabinet isn’t answering')
    expect(reach.misses).toBe(0)
  })
})

describe('the words', () => {
  const at = () => '4:12 PM'
  const base = { out: false, lost: false, since: 1, heard: 1, phone: false, anywhere: false, at }

  it('say nothing while everything gets through', () => {
    expect(bandFor(base)).toBeNull()
  })

  it('on a wall, cut off but still hearing the house: what you see is current, use the switch', () => {
    expect(bandFor({ ...base, out: true })).toEqual({
      title: 'Changes made here aren’t reaching the hub',
      body: 'Since 4:12 PM. What you see is up to date, and this screen keeps trying. The switches on the wall still work.',
      hushed: false,
    })
  })

  it('on a wall, hearing nothing either: when it last heard, and the room hushed', () => {
    expect(bandFor({ ...base, lost: true })).toEqual({
      title: 'This screen can’t reach the hub',
      body: 'Last heard from it at 4:12 PM, so what you see may have changed since. It keeps trying. The switches on the wall still work.',
      hushed: true,
    })
  })

  it('on a phone at home, the likeliest fix is the Wi-Fi; on one that works anywhere, it is not', () => {
    expect(bandFor({ ...base, out: true, phone: true })?.body).toBe('Since 4:12 PM. It uses the house on your home Wi‑Fi, so check that it’s connected. It keeps trying on its own.')
    expect(bandFor({ ...base, out: true, phone: true, anywhere: true })?.body).toBe('Since 4:12 PM. It keeps trying on its own.')
    expect(bandFor({ ...base, out: true, phone: true })?.title).toBe('This phone can’t reach the hub')
  })

  it('in the corner, Connected only while changes get through', () => {
    expect(linkWord(true, false, false)).toEqual({ word: 'Connected', cls: 'up' })
    expect(linkWord(true, false, true)).toEqual({ word: 'Can’t reach the hub', cls: 'out' })
    expect(linkWord(false, true, false)).toEqual({ word: 'Can’t reach the hub', cls: 'out' })
    expect(linkWord(false, false, false)).toEqual({ word: 'Reconnecting', cls: '' })
  })

  it('on the card that did not get through', () => {
    expect(stillLine(true)).toEqual({ said: 'Still on', why: 'Changes can’t get through. Use the switch.' })
    expect(stillLine(false).said).toBe('Still off')
  })
})
