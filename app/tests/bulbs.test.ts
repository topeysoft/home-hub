// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A bulb that can do color, drawn in the color it says it is.
   The hub has always sent rgb_color; the panel read it off the wire and threw it
   away, so a magenta lamp and a 2700K one were the same amber picture. These pin
   the repair, and in particular the two ways it could go wrong quietly: drawing
   every warm white bulb as "colored", and drawing a deep color as an unlit lamp. */
import { describe, expect, it } from 'vitest'
import { bulbColor, device, emitId, emitRamp, materials, LIGHT_KINDS } from '../src/art'

const M = materials(-4, 'cloudy')
const PINK: [number, number, number] = [226, 72, 184]
const fills = (kind: any, state: any) =>
  device(kind, state, M).marks.map(m => String(m.at.fill ?? m.at.stroke ?? '')).join(' ')

describe('whether a light is showing a color', () => {
  it('takes the color when the bulb is in a color mode', () => {
    expect(bulbColor({ color_mode: 'hs', rgb_color: PINK })).toEqual(PINK)
    for (const mode of ['rgb', 'rgbw', 'rgbww', 'xy'])
      expect(bulbColor({ color_mode: mode, rgb_color: PINK })).toEqual(PINK)
  })

  /* The trap this exists to avoid. Home Assistant reports rgb_color in
     color_temp mode too -- it is the RGB rendering of the white point, which
     nobody chose. Treating it as a color turns every warm white bulb in every
     house into a "colored" lamp the moment this ships. */
  it('ignores the white point a warm white bulb reports', () => {
    expect(bulbColor({ color_mode: 'color_temp', color_temp_kelvin: 2700, rgb_color: [255, 180, 107] })).toBeUndefined()
    expect(bulbColor({ color_mode: 'brightness', rgb_color: [255, 214, 170] })).toBeUndefined()
  })

  /* A hub older than this panel sends no color_mode at all. Rather than guessing
     wrong in the loud direction, fall back to the tell HA leaves anyway: a bulb
     in a color mode reports no color_temp_kelvin. */
  it('falls back sensibly for a hub that does not send color_mode', () => {
    expect(bulbColor({ rgb_color: PINK })).toEqual(PINK)
    expect(bulbColor({ rgb_color: [255, 180, 107], color_temp_kelvin: 2700 })).toBeUndefined()
  })

  it('is not fooled by a missing or malformed color', () => {
    for (const attrs of [undefined, null, {}, { rgb_color: null }, { rgb_color: [1, 2] }, { rgb_color: 'red' },
      { rgb_color: [226, 'x', 184] }] as any[])
      expect(bulbColor(attrs)).toBeUndefined()
  })
})

describe('what it is drawn with', () => {
  /* An SVG gradient is addressed by id across the whole document, so a colored
     bulb cannot be handed a colored copy of the shared one -- it needs its own,
     and ArtDefs declares it under this id. Two lamps set alike must land on the
     same id or the defs grow one entry per bulb instead of one per color. */
  it('gives a color a stable id, shared by every bulb set to it', () => {
    expect(emitId(PINK)).toBe('e248b8')
    expect(emitId([...PINK] as any)).toBe(emitId(PINK))
    expect(emitId([0, 0, 0])).toBe('000000')
    expect(emitId([300, -5, 12.6] as any)).toBe('ff000d')     // clamped and rounded, never a broken id
  })

  it('paints a colored bulb from its own gradients', () => {
    for (const kind of LIGHT_KINDS) {
      const f = fills(kind, { on: true, brightness: 1, color: PINK })
      expect(f).toContain(`-${emitId(PINK)}`)                 // its own set
      expect(f).not.toMatch(/url\(#m(Pool|Cone|Glass)\)/)     // and not the shared warm one
    }
  })

  /* No color, nothing changes. Every house without a color bulb must draw exactly
     what it drew before, out of the one shared set. */
  it('leaves a lamp that has no color of its own alone', () => {
    for (const kind of LIGHT_KINDS) {
      const f = fills(kind, { on: true, brightness: 1 })
      expect(f).not.toContain('-e248b8')
      expect(f).not.toMatch(/url\(#m(Pool|Cone|Glass)-/)
    }
  })

  /* Off is off -- the rule art.test.ts already holds every kind to. A colored
     bulb must not find a way around it: an unlit lamp emits nothing, whatever
     color it was last set to. */
  it('emits nothing when a colored bulb is off', () => {
    for (const kind of LIGHT_KINDS) {
      expect(device(kind, { on: false, color: PINK }, M).glow).toBe(0)
      expect(fills(kind, { on: false, color: PINK })).not.toMatch(/url\(#m(Pool|Cone|Glass)-/)
    }
  })
})

describe('the ramp a color is carried on', () => {
  /* The shape of the warm ramp is what makes a lamp read as a light source: hot
     and near-white in the middle, the color itself further out. Keeping that
     shape is also what stops a deep blue bulb from being drawn as an unlit one,
     which is the failure that would look like a bug rather than a color. */
  it('blows out toward white in the middle, whatever the hue', () => {
    const lum = (s: string) => {
      const [r, g, b] = s.match(/\d+/g)!.slice(0, 3).map(Number)
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    for (const c of [[226, 72, 184], [20, 20, 200], [0, 90, 40], [255, 0, 0]] as [number, number, number][]) {
      const r = emitRamp(c)
      expect(lum(r.lit)).toBeGreaterThan(lum(r.lamp))
      expect(lum(r.glow)).toBeGreaterThan(lum(r.lamp))
      expect(lum(r.lit)).toBeGreaterThan(150)                 // a source, not a dark shape
    }
  })

  /* And the far edge is the bulb's actual color, not an approximation of it:
     that is the one stop a person can compare against the lamp in the room. */
  it('keeps the bulb’s own color at the edge', () => {
    expect(emitRamp(PINK).lamp).toContain('226')
    expect(emitRamp(PINK).lamp).toContain('72')
    expect(emitRamp(PINK).lamp).toContain('184')
  })
})
