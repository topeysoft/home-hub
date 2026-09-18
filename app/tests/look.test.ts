// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* One feel, and a screen that arranges itself.

   Two rules carry this file, and both were learned the hard way.

   A feel must survive a hub that has never heard of feels. The hub keeps only
   the keys it knows (LOOK in brain/hub/api.py) and drops the rest, which is
   correct and is also why a panel must not depend on the one key that names the
   feel: against a hub one version behind, every pick on the Look page reverted
   to Calm instantly, with no error and nothing on screen to explain it. A feel
   IS a face and a tone, so it is read back out of those instead.

   And a screen arranges itself. That is the half of the old Look page that was
   never taste, and the tests below hold it to the seams look.ts names rather
   than to whatever the function happens to do today. */
import { describe, expect, it } from 'vitest'
import { FEELS, adjusted, feelFrom, isFeel, lookOf, placeOf, READ_AT, TOUCHED_AT } from '../src/look'

describe('the three looks', () => {
  it('offers three, each one a face and a tone', () => {
    expect(FEELS).toHaveLength(3)
    for (const f of FEELS) {
      expect(isFeel(f.id)).toBe(true)
      expect(f.label.length).toBeGreaterThan(0)
      expect(f.hint.length).toBeGreaterThan(0)
    }
  })

  /* The picker shows all three live, side by side, at whatever hour it is opened.
     Two feels that resolve to the same face and tone are the same picture twice,
     and that is what retired Cozy: `follow` is warm after sunset, so from dusk to
     dawn Cozy and Calm were indistinguishable. */
  it('never offers the same look under two names', () => {
    const made = FEELS.map(f => `${f.face}/${f.tone}`)
    expect(new Set(made).size).toBe(FEELS.length)
  })
})

describe('a feel read back from a hub', () => {
  it('is found by name when the hub kept the name', () => {
    for (const f of FEELS) expect(feelFrom({ feel: f.id }).id).toBe(f.id)
  })

  /* The regression. An older hub answers with a look that has no feel in it at
     all; the panel has to work that out from what did come back. */
  it('is found from the face and the tone when the hub dropped the name', () => {
    for (const f of FEELS) {
      expect(feelFrom({ face: f.face, tone: f.tone }).id).toBe(f.id)
      expect(feelFrom({ feel: undefined, face: f.face, tone: f.tone }).id).toBe(f.id)
    }
  })

  it('survives the round trip through a hub that keeps only what it understands', () => {
    for (const f of FEELS) {
      const sent = lookOf(f.id)
      for (const keys of [['tone', 'face'], ['tone', 'face', 'layout', 'nav'], ['feel', 'tone', 'face', 'layout', 'nav']]) {
        const kept = Object.fromEntries(Object.entries(sent).filter(([k]) => keys.includes(k)))
        expect(feelFrom(kept).id).toBe(f.id)
      }
    }
  })

  it('lands somewhere real rather than nowhere, for a look it cannot place at all', () => {
    expect(isFeel(feelFrom(undefined).id)).toBe(true)
    expect(isFeel(feelFrom({}).id)).toBe(true)
    expect(isFeel(feelFrom({ feel: 'kittens', face: 'velvet', tone: 'kittens' }).id)).toBe(true)
  })
})

describe('what counts as adjusted', () => {
  it('is not adjusted when the look is exactly what the feel resolves to', () => {
    for (const f of FEELS) expect(adjusted(lookOf(f.id))).toBe(false)
  })

  it('is adjusted when a dial was set by hand', () => {
    expect(adjusted({ ...lookOf('calm'), tone: 'cool' })).toBe(true)
    expect(adjusted({ ...lookOf('calm'), layout: 'rail' })).toBe(true)
    expect(adjusted({ ...lookOf('nightfall'), nav: 'side' })).toBe(true)
  })

  /* A house that set its look by hand before feels existed stored a real layout
     rather than "auto". Nothing may quietly overrule that, and the page has to
     be able to say so. */
  it('is adjusted for a house that chose its arrangement before feels existed', () => {
    expect(adjusted({ tone: 'warm', layout: 'rail', nav: 'top' })).toBe(true)
  })
})

describe('where the screen is', () => {
  it('gives a phone the column, and the rail that folds across its top', () => {
    expect(placeOf(390)).toEqual({ layout: 'stack', nav: 'side' })
    expect(placeOf(TOUCHED_AT - 1)).toEqual({ layout: 'stack', nav: 'side' })
  })

  it('gives a screen within reach the row it sweeps through', () => {
    expect(placeOf(TOUCHED_AT)).toEqual({ layout: 'rail', nav: 'top' })
    expect(placeOf(READ_AT - 1)).toEqual({ layout: 'rail', nav: 'top' })
  })

  it('gives a screen read from across the room the wall', () => {
    expect(placeOf(READ_AT)).toEqual({ layout: 'wall', nav: 'top' })
    expect(placeOf(2560)).toEqual({ layout: 'wall', nav: 'top' })
  })

  it('answers for every width, and only ever with arrangements that exist', () => {
    for (let w = 200; w <= 3000; w += 7) {
      const { layout, nav } = placeOf(w)
      expect(['stack', 'rail', 'wall']).toContain(layout)
      expect(['side', 'top']).toContain(nav)
    }
  })

  /* The arrangement is the screen's answer, so a feel must never carry one. */
  it('hands the arrangement back to the screen whichever feel is picked', () => {
    for (const f of FEELS) {
      expect(lookOf(f.id).layout).toBe('auto')
      expect(lookOf(f.id).nav).toBe('auto')
    }
  })
})
