// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What happened draws what the brain hands it and decides two things for itself. These are those two.
   The rest of the page is deliberately untestable here because there is nothing in it to test: the
   sentences, the group headings and the buttons' words all arrive over the wire, which is the point
   of them arriving over the wire. brain/tests/test_happened.py is where those are held shut. */
import { describe, expect, it } from 'vitest'
import { didWhat, iconFor } from '../src/happened'
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

describe('what a tap says afterwards', () => {
  it('names what was actually done', () => {
    expect(didWhat('off')).toBe('Turned off.')
    expect(didWhat('lock')).toBe('Locked.')
  })

  it('does not claim a blind has finished closing, because it has not', () => {
    /* A cover takes a quarter of a minute to run and the panel is told the moment the call is
       accepted. "Closed." would be a thing the row says while the door is still moving. */
    expect(didWhat('close')).toBe('Closing.')
  })

  it('says something rather than nothing when the act had no argument', () => {
    expect(didWhat(undefined)).toBe('Turned off.')
  })
})
