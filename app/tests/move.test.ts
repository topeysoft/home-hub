// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Moving a phone to the house's own name, as design/away/ chose it on 1 October (C), and the door the app
   then reaches the hub through. These fail on purpose if the rules drift from the boards: the band line is
   for every phone of the house but the wall, the switch is for whoever keeps the house, the away screen waits
   only for a phone the house knows, and a page only ever looks for the hub at home once it carries a token. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Me, Phone } from '../src/api'
import { appHost, offerMove, moveCode, switchFor, waitsToBeLetOut, withoutCode } from '../src/move'
import { apiUrl, door, learnLan, look, looks, moved, withToken, wsProtocols, wsUrl } from '../src/door'

const phone = (over: Partial<Phone> = {}): Phone => ({ id: 'p1', name: "Temi's iPhone", kind: 'phone', joined: 0, expires: null, remote: false, last_seen: null, how: 'code', me: true, ...over })
const me = (over: Partial<Me> = {}): Me => ({ locked: true, paired: true, home: 'Main Palace', phone: phone(), address: 'https://main-palace.elyir.app', lan: '192-168-86-53.main-palace.home.elyir.app', ...over })

describe('the band line', () => {
  it('is for a phone of the house that is not in the Houses app yet, anywhere but inside the app', () => {
    expect(offerMove(me(), false)).toBe(true)
    expect(offerMove(me(), true)).toBe(false)
    expect(offerMove(me({ phone: phone({ in_app: true }) }), false)).toBe(false)
  })
  it('is offered once more to a phone that moved only to the house\'s own name, before 3 October', () => {
    expect(offerMove(me({ phone: phone({ moved: true, in_app: false }) }), false)).toBe(true)
  })
  it('is never for the wall, which stays home, nor before the house has an address', () => {
    expect(offerMove(me({ phone: phone({ kind: 'wall' }) }), false)).toBe(false)
    expect(offerMove(me({ address: null }), false)).toBe(false)
    expect(offerMove(me({ phone: null }), false)).toBe(false)
  })
  it('names the app in the house\'s own zone', () => {
    expect(appHost('https://main-palace.elyir.app')).toBe('houses.elyir.app')
    expect(appHost(null)).toBe('')
  })
})

describe('the code a move arrives with', () => {
  it('is read once and taken out of the address', () => {
    expect(moveCode('?move=abc')).toBe('abc')
    expect(moveCode('?x=1')).toBeNull()
    expect(withoutCode('https://main-palace.elyir.app/?move=abc')).toBe('/')
    expect(withoutCode('https://main-palace.elyir.app/?sheet=hub&move=abc#x')).toBe('/?sheet=hub#x')
  })
})

describe('Home only or Anywhere, on People', () => {
  it('is for phones, once the house has an address, on a screen that keeps the house', () => {
    expect(switchFor(phone(), true, true)).toBe(true)
    expect(switchFor(phone({ kind: 'wall' }), true, true)).toBe(false)
    expect(switchFor(phone(), false, true)).toBe(false)
    expect(switchFor(phone(), true, false)).toBe(false)
  })
})

describe('the away screen', () => {
  it('waits, and opens by itself, only for a phone the house knows', () => {
    expect(waitsToBeLetOut('This phone works on your home Wi‑Fi. Someone with the passcode can set it to Anywhere, in People.')).toBe(true)
    expect(waitsToBeLetOut('This house isn’t open to this phone.')).toBe(false)
    expect(waitsToBeLetOut(null)).toBe(false)
  })
})

describe('the door', () => {
  afterEach(() => { moved('', null); door.base = ''; vi.unstubAllGlobals() })

  it('carries nothing and looks for nothing on a page that has no token -- hub.local is already home', () => {
    learnLan('192-168-86-53.main-palace.home.elyir.app')
    expect(looks()).toBe(false)
    expect(withToken(new Headers()).has('Authorization')).toBe(false)
    expect(wsProtocols()).toBeUndefined()
    expect(apiUrl('/home')).toBe('/home')
  })

  it('once moved, sends the token as a header and as a subprotocol, never in a URL', () => {
    moved('tok', '192-168-86-53.main-palace.home.elyir.app')
    expect(withToken(new Headers()).get('Authorization')).toBe('Bearer tok')
    expect(wsProtocols()).toEqual(['hub', 'tok'])
    door.base = 'https://192-168-86-53.main-palace.home.elyir.app'
    expect(wsUrl('/stream')).toBe('wss://192-168-86-53.main-palace.home.elyir.app/stream')
    expect(apiUrl('/home')).toBe('https://192-168-86-53.main-palace.home.elyir.app/home')
    expect(wsUrl('/stream')).not.toContain('tok')
  })

  it('learns only a name that is a home name', () => {
    learnLan('evil.example.com')
    expect(door.lan).toBe('')
    learnLan('192-168-86-53.main-palace.home.elyir.app')
    expect(door.lan).toBe('192-168-86-53.main-palace.home.elyir.app')
  })

  it('uses the hub at home while it answers, and the relay when it does not', async () => {
    moved('tok', '192-168-86-53.main-palace.home.elyir.app')
    vi.stubGlobal('location', { protocol: 'https:', hostname: 'main-palace.elyir.app', host: 'main-palace.elyir.app' })
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"ok":true}', { status: 200 })))
    await look()
    expect(door.base).toBe('https://192-168-86-53.main-palace.home.elyir.app')
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('unreachable') }))
    await look()
    expect(door.base).toBe('')
  })
})
