// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Asking a light to be a color, which the panel could not do at all until now.
   The two that matter most are the ones that would be quiet failures: a light
   nobody has touched must read as Automatic rather than as whatever the bulb
   happens to sit at, and white must be reachable from a bulb that is currently
   pink -- the way back used to disappear with the Warmth column. */
import { describe, expect, it } from 'vitest'
import { COLORS, WHITES, autoKelvin, dataFor, guessFor, handlesOf, hsRgb, kelvinRgb, same, wantedOf, wantedRgb, type Wanted } from '../src/color'

describe('what a light is currently on', () => {
  /* The whole reason the house keeps its own flag. A bulb sitting at 2700K cannot
     be told from one somebody deliberately set to 2700K by looking at the bulb;
     the difference is who decided, and only the house knows that. */
  it('is Automatic until somebody says otherwise', () => {
    expect(wantedOf({}).kind).toBe('auto')
    expect(wantedOf({ color_temp_kelvin: 2700 }).kind).toBe('auto')
    expect(wantedOf({ hs_color: [312, 66], rgb_color: [226, 72, 184] }).kind).toBe('auto')
    expect(wantedOf(null).kind).toBe('auto')
  })

  it('and reads what was pinned once it has been', () => {
    expect(wantedOf({ color_pinned: true, hs_color: [312, 66] })).toEqual({ kind: 'color', hue: 312, amount: 66 })
    expect(wantedOf({ color_pinned: true, color_temp_kelvin: 4000 })).toEqual({ kind: 'white', kelvin: 4000 })
  })

  /* saturation 0 is a white however it arrives, and must not be drawn as a color
     with the amount column at the bottom */
  it('treats a pinned bulb at zero saturation as a white, not a color', () => {
    expect(wantedOf({ color_pinned: true, hs_color: [312, 0], color_temp_kelvin: 2700 }).kind).toBe('white')
  })
})

describe('what gets sent', () => {
  it('asks for a color as hue and amount, which is what the house takes', () => {
    expect(dataFor({ kind: 'color', hue: 312.4, amount: 66.2 })).toEqual({ hs_color: [312, 66], color_pinned: true })
  })

  it('asks for a white as a temperature', () => {
    expect(dataFor({ kind: 'white', kelvin: 4000 })).toEqual({ color_temp_kelvin: 4000, color_pinned: true })
  })

  /* Automatic is a change you can SEE, not only a record: without this the lamp
     would sit on yesterday's color until the next thing happened to it. */
  it('sends a real white when a light is put back on Automatic', () => {
    expect(dataFor({ kind: 'auto' }, 2400)).toEqual({ color_temp_kelvin: 2400, color_pinned: false })
  })

  /* The hub keeps the pin because a bulb cannot: one sitting at 2700K is the same to look at as
     one somebody deliberately set to 2700K, and the difference is who decided. It rides on the
     same call and api.py takes it off before the driver sees it. */
  /* and the pin travels with it, in both directions */
  it('pins on a choice and unpins on Automatic', () => {
    expect(guessFor({ kind: 'color', hue: 312, amount: 66 }).color_pinned).toBe(true)
    expect(guessFor({ kind: 'white', kelvin: 2700 }).color_pinned).toBe(true)
    expect(guessFor({ kind: 'auto' }).color_pinned).toBe(false)
  })

  /* The leak this closes. A bulb in hs mode reports no color_temp_kelvin, which is
     what used to make the Warmth column vanish and left no way back to white. The
     guess has to clear the other mode's attribute or the pane would show a lamp as
     both at once. */
  it('leaves no trace of the other mode behind', () => {
    expect(guessFor({ kind: 'color', hue: 312, amount: 66 }).color_temp_kelvin).toBeNull()
    expect(guessFor({ kind: 'white', kelvin: 2700 }).hs_color).toBeNull()
  })
})

describe('the twelve, and the thirteenth', () => {
  it('offers eight colors and four whites', () => {
    expect(COLORS).toHaveLength(8)
    expect(WHITES).toHaveLength(4)
  })

  /* evenly round the wheel, so no swatch is louder than its neighbor and the row
     reads as a set rather than a ranking */
  it('spaces the colors round the wheel rather than bunching them', () => {
    const hues = COLORS.map(c => c.hue).sort((a, b) => a - b)
    const gaps = hues.map((h, i) => (((i === hues.length - 1 ? hues[0] + 360 : hues[i + 1]) - h) + 360) % 360)
    for (const g of gaps) expect(g, `hues: ${hues.join(', ')}`).toBeGreaterThan(20)
  })

  /* none of them is a white by accident: that is what the other row is for */
  it('keeps every color clearly a color', () => {
    for (const c of COLORS) expect(c.amount, `hue ${c.hue}`).toBeGreaterThan(40)
  })

  /* the two columns open on what the lamp is showing, so the first thing a finger
     does is a nudge rather than a jump -- which is the whole point of tuning */
  it('opens the columns where the lamp already is', () => {
    expect(handlesOf({ kind: 'color', hue: 312, amount: 66 })).toEqual({ hue: 312, amount: 66 })
  })

  it('and somewhere sensible for a lamp that has no color of its own', () => {
    const h = handlesOf({ kind: 'auto' })
    expect(h.hue).toBeGreaterThanOrEqual(0)
    expect(h.amount).toBeGreaterThan(0)
    expect(h.amount).toBeLessThan(100)
  })
})

describe('drawing it', () => {
  it('turns a hue into the color it is', () => {
    expect(hsRgb(0, 100)).toEqual([255, 0, 0])
    expect(hsRgb(120, 100)).toEqual([0, 255, 0])
    expect(hsRgb(240, 100)).toEqual([0, 0, 255])
  })

  it('and no amount at all into white', () => {
    expect(hsRgb(312, 0)).toEqual([255, 255, 255])
  })

  it('wraps rather than breaking on a hue past the wheel', () => {
    expect(hsRgb(360, 100)).toEqual(hsRgb(0, 100))
    expect(hsRgb(-40, 100)).toEqual(hsRgb(320, 100))
  })

  /* 2200K has to look like a candle and 6500K like daylight, or the four white
     swatches are four identical circles */
  it('keeps the warm end warm and the cool end cool', () => {
    const warm = kelvinRgb(2200), cool = kelvinRgb(6500)
    expect(warm[0] - warm[2], 'a warm white leans red').toBeGreaterThan(60)
    expect(cool[2] - cool[0], 'a cool white leans blue').toBeGreaterThan(10)
  })

  /* Automatic has no color of its own -- it is whatever the hour gives it */
  it('draws Automatic as the white the house would pick', () => {
    expect(wantedRgb({ kind: 'auto' }, 2200)).toEqual(kelvinRgb(2200))
    expect(wantedRgb({ kind: 'auto' }, 6500)).toEqual(kelvinRgb(6500))
  })
})

describe('what Automatic means right now', () => {
  /* "Follow the light -- cool and open by day, lamplit after sunset" is the tone's
     own label, and a lamp on Automatic has to mean the same thing by it, off the
     same input. A lamp and a card disagreeing about the hour is worse than either
     being wrong alone. */
  it('is lamplight after dark and cooler by day', () => {
    expect(autoKelvin(-8)).toBeLessThan(autoKelvin(0))
    expect(autoKelvin(0)).toBeLessThan(autoKelvin(40))
  })

  it('and stays inside what a domestic bulb can do', () => {
    for (const el of [-90, -8, 0, 20, 90])
      expect(autoKelvin(el), `elevation ${el}`).toBeGreaterThanOrEqual(2000)
    for (const el of [-90, -8, 0, 20, 90])
      expect(autoKelvin(el), `elevation ${el}`).toBeLessThanOrEqual(6500)
  })
})

describe('which swatch wears the ring', () => {
  /* A lamp reports back what it actually managed, which is rarely the exact hue
     it was asked for. A swatch that stops looking chosen the moment the bulb
     answers is worse than one that is a degree out. */
  it('forgives a bulb that answers a degree off what it was asked', () => {
    const asked: Wanted = { kind: 'color', hue: 312, amount: 66 }
    expect(same(asked, { kind: 'color', hue: 316, amount: 69 })).toBe(true)
    expect(same(asked, { kind: 'white', kelvin: 2700 })).toBe(false)
  })

  it('but does not call two different colors the same', () => {
    expect(same({ kind: 'color', hue: 312, amount: 66 }, { kind: 'color', hue: 168, amount: 62 })).toBe(false)
  })

  /* round the top of the wheel, where 358 and 2 are four degrees apart */
  it('knows 358 and 2 are neighbors', () => {
    expect(same({ kind: 'color', hue: 358, amount: 70 }, { kind: 'color', hue: 2, amount: 70 })).toBe(true)
  })

  it('and treats every Automatic as the same Automatic', () => {
    expect(same({ kind: 'auto' }, { kind: 'auto' })).toBe(true)
  })
})
