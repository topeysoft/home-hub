// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What a thermostat wears, and why it is that and not something else.
   The card used to be colored by the MODE -- what the box was set to -- so one
   holding at temperature sat fully blue with nothing running. These pin the
   repair: the ACTION decides, idle is not a color, and the card is drawn at the
   distance design/nightfall page 3 argues for rather than a fixed blue. */
import { describe, expect, it } from 'vitest'
import { actingOf, toneVars } from '../src/tone'
import { ground, oklch } from '../src/sky'

const DUSK = { el: -4, wx: 'cloudy' }          // the hour every board on page 3 is drawn at
const NOON = { el: 52, wx: 'sunny' }

describe('what the thermostat is doing', () => {
  it('colors by the action, not by the mode', () => {
    expect(actingOf('cooling')).toBe('act-cooling')
    expect(actingOf('heating')).toBe('act-heating')
  })

  /* The whole point of the change. A box set to cool that has reached temperature
     reports mode `cool` and action `idle`; the words have always said Holding and
     the dial arc has always vanished, while the card stayed blue. */
  it('wears nothing while it is holding', () => {
    expect(actingOf('idle')).toBe('')
  })

  /* Running, but not moving the temperature. Neither deserves the signal. */
  it('wears nothing for fan or drying', () => {
    expect(actingOf('fan')).toBe('')
    expect(actingOf('drying')).toBe('')
  })

  /* Warming up and defrosting ARE the heat coming on, whatever they are called. */
  it('counts preheating and defrosting as heating', () => {
    expect(actingOf('preheating')).toBe('act-heating')
    expect(actingOf('defrosting')).toBe('act-heating')
  })

  /* Not a regression for the many thermostats that report no hvac_action at all.
     The caller passes `hvac_action ?? mode`, so with nothing to go on the bare
     mode arrives here and still colors exactly as it did before. */
  it('still colors by the bare mode when the box reports no action', () => {
    expect(actingOf('cool')).toBe('act-cooling')
    expect(actingOf('heat')).toBe('act-heating')
    expect(actingOf(undefined)).toBe('')
    expect(actingOf(null)).toBe('')
  })

  /* panel.css is one flat global sheet and `.idle` in it is the REST SCREEN, at
     position:absolute inset:0 z-index:50. A bare state name here would hand a
     thermostat the screensaver's geometry with both screens still rendering and
     nothing failing anywhere. If this ever returns an un-prefixed name, that is
     the bug, not a tidy-up. */
  it('namespaces every name it returns', () => {
    for (const d of ['cooling', 'heating', 'cool', 'heat', 'preheating', 'defrosting', 'idle', 'fan'])
      expect(actingOf(d) === '' || actingOf(d).startsWith('act-')).toBe(true)
  })
})

describe('the card it is drawn on', () => {
  /* Never an absolute color: the same rule every other card here holds to. A
     fixed blue is a lit surface at midnight and a hole in the daylight by noon. */
  it('holds a fixed distance from the sky rather than a fixed color', () => {
    const at = (s: typeof DUSK) => {
      const v = toneVars(s.el, s.wx)['--card-cooling']
      return Number(/oklch\(([\d.]+)/.exec(v.split('),')[1])![1])   // the second stop, the card's own L
    }
    const dusk = at(DUSK), noon = at(NOON)
    expect(noon).toBeGreaterThan(dusk)                               // it lightens with the day
    for (const s of [DUSK, NOON])
      expect(at(s) - oklch(ground(s.el, s.wx)).L).toBeCloseTo(0.30, 2)
  })

  /* Louder than a tone card on purpose, and measured rather than felt: this is
     the one card read from the far side of a room, and what it replaced was a
     smudge at three metres. */
  it('is drawn at the distance the board argues for', () => {
    const v = toneVars(DUSK.el, DUSK.wx)['--card-cooling']
    expect(v).toContain('0.085')                                     // chroma, against a tone's ~.05
    expect(toneVars(DUSK.el, DUSK.wx)['--card-heating']).toContain('0.085')
  })

  /* Cooling is blue and heating is warm at every hour and in every tone. These
     are signals; Warm and Cool must not be able to disagree about what blue
     means. The hues are panel.css's own --tint values, read back as oklch. */
  it('keeps the same two hues whatever the tone', () => {
    for (const tone of ['follow', 'warm', 'cool', 'pastel'] as const) {
      expect(toneVars(DUSK.el, DUSK.wx, tone)['--card-cooling']).toContain(' 250)')
      expect(toneVars(DUSK.el, DUSK.wx, tone)['--card-heating']).toContain(' 55)')
    }
  })

  /* It sits further from the sky than a tone card does, so it crosses the flip at
     a different hour and cannot borrow their answer. Dark type by noon or the
     number is unreadable on a bright day. */
  it('flips its own ink, at its own lightness', () => {
    expect(toneVars(DUSK.el, DUSK.wx)['--act-ink']).toBe('#f1eee8')
    expect(toneVars(NOON.el, NOON.wx)['--act-ink']).toBe('#1e1b24')
  })
})
