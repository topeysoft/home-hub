// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What happened draws what the brain hands it and decides two things for itself. These are those two.
   The rest of the page is deliberately untestable here because there is nothing in it to test: the
   sentences, the group headings and the buttons' words all arrive over the wire, which is the point
   of them arriving over the wire. brain/tests/test_happened.py is where those are held shut. */
import { describe, expect, it } from 'vitest'
import { guessFor, iconFor } from '../src/happened'
import type { HappenedItem } from '../src/api'

const item = (over: Partial<HappenedItem> = {}): HappenedItem =>
  ({ kind: 'still', subject: 'light.porch', text: '', when: 'now', ts: 0, acts: [], ...over })

describe('which glyph a finding wears', () => {
  it('follows what the thing was left AS, not what sort of thing it is', () => {
    expect(iconFor(item({ word: 'on' }))).toBe('light')
    expect(iconFor(item({ word: 'unlocked' }))).toBe('lock')
    expect(iconFor(item({ word: 'open' }))).toBe('home')
  })

  it('draws a phone for the people group', () => {
    expect(iconFor(item({ kind: 'phone', word: undefined }))).toBe('phone')
  })

  it('has an answer for a word it has never seen', () => {
    /* The brain may grow a new sort of thing to notice before this file hears about it. A row with
       no glyph would not draw at all, which is a worse way to find out than a plain one. */
    expect(iconFor(item({ word: 'running' }))).toBe('light')
    expect(iconFor(item({ word: undefined }))).toBe('light')
  })
})

describe('what the row will read as before the house has answered', () => {
  it('guesses the state each act lands on', () => {
    expect(guessFor('off')).toEqual({ state: 'off' })
    expect(guessFor('lock')).toEqual({ state: 'locked' })
    expect(guessFor('close')).toEqual({ state: 'closed' })
  })

  it('guesses off when the act carried no argument', () => {
    expect(guessFor(undefined)).toEqual({ state: 'off' })
  })

  /* The WORDS a quieted row says are deliberately not in this file. They are the store's `done` map
     and doneLine(), shared with Home -- a second copy here would disagree with Home about a light
     they both show, and would go on saying it after the wall had gone to rest. */
  it('does not carry the wording: that is the store\'s, and shared with Home', async () => {
    const src = await import('node:fs').then(fs => fs.readFileSync('src/happened.ts', 'utf8'))
    expect(src).not.toMatch(/Turned off|Locked\.|Closed \u00b7/)
  })
})
