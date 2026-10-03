// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'
import { addLink, codeOf, houseToOpen, iphoneSafari, labelOf, originOf } from '../houses/src/houses'

/* The Houses app's rules, pinned to design/houses/ (B, and The app). */

describe('the code', () => {
  it('is what a person typed, without how they read it aloud', () => {
    expect(codeOf('k7q4 - mpwr')).toBe('K7Q4MPWR')
  })
  it('arrives with the house in the fragment, and only a whole one counts', () => {
    expect(addLink('#h=main-palace&c=K7Q4MPWR')).toEqual({ house: 'main-palace', code: 'K7Q4MPWR' })
    expect(addLink('#h=main-palace&c=K7Q4')).toBeNull()
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
