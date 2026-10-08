// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Light or dark (design/appearance/, B, decided 7 October): which screen gets which, and what the
   light shade promises at every hour -- a sky that never goes dark, cards and panes that keep dark
   ink readable, and a token block that leaves nothing on the page drawn for a dark field. */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { defaultChoice, isShadeChoice, shadeOf } from '../src/shade'
import { COND, ground, oklch, palette, wxOf } from '../src/sky'
import { glassVars, toneVars, type ToneName } from '../src/tone'

const ELEVATIONS = [-40, -18, -9, -3, 0, 6, 15, 40, 89]
const CONDITIONS = Object.keys(COND)
const TONES: ToneName[] = ['warm', 'cool', 'pastel', 'follow']

describe('which screen is light', () => {
  it('a wall that nobody has set stays dark, as every wall was before', () => {
    expect(defaultChoice(true)).toBe('dark')
    expect(shadeOf(null, true, false)).toBe('dark')
  })
  it('a phone follows the phone until somebody picks', () => {
    expect(shadeOf(null, false, false)).toBe('light')
    expect(shadeOf(null, false, true)).toBe('dark')
  })
  it('what was picked on this screen wins over the default, either way round', () => {
    expect(shadeOf('light', true, true)).toBe('light')
    expect(shadeOf('dark', false, false)).toBe('dark')
    expect(shadeOf('auto', true, false)).toBe('light')
  })
  it('a preview wins over everything, and nonsense is ignored', () => {
    expect(shadeOf('dark', true, true, 'light')).toBe('light')
    expect(shadeOf('purple', true, false, 'nope')).toBe('dark')
    expect(isShadeChoice('auto')).toBe(true)
    expect(isShadeChoice('Light')).toBe(false)
  })
})

describe('the held sky', () => {
  it('never goes dark, at any hour, in any weather', () => {
    for (const el of ELEVATIONS) for (const c of CONDITIONS)
      for (const band of palette(el, wxOf(c), 'light')) expect(oklch(band).L).toBeGreaterThan(0.62)
  })
  it('still says what hour it is: noon is lighter than midnight', () => {
    const top = (el: number) => oklch(palette(el, wxOf('sunny'), 'light')[0]).L
    expect(top(40)).toBeGreaterThan(top(-18) + 0.04)
  })
  it('keeps the hour in its hue: dusk is warm at the horizon, noon is blue overhead', () => {
    const dusk = oklch(palette(-3, wxOf('sunny'), 'light')[2]).H
    const noon = oklch(palette(40, wxOf('sunny'), 'light')[0]).H
    expect(dusk).toBeLessThan(90)
    expect(noon).toBeGreaterThan(200)
    expect(noon).toBeLessThan(280)
  })
  it('has no veil: a card is laid on the sky itself', () => {
    expect(ground(40, 'sunny', 'light')).toEqual(palette(40, wxOf('sunny'), 'light')[1])
  })
  it('leaves the dark sky exactly as it was', () => {
    expect(palette(-3, wxOf('cloudy'))).toEqual(palette(-3, wxOf('cloudy'), 'dark'))
  })
})

/* contrast of #1e1b24 on a gray of lightness L: oklch L is the cube root of relative luminance */
const onLight = (L: number) => (L ** 3 + 0.05) / (0.0119 + 0.05)

describe('cards and panes on the light sky', () => {
  it('carry dark ink on paper at every hour, and it reads', () => {
    for (const el of ELEVATIONS) for (const c of CONDITIONS) for (const t of TONES) {
      const v = toneVars(el, c, t, 'light')
      expect(v['--card-ink']).toBe('#1e1b24')
      expect(onLight(Number(v['--card-l']))).toBeGreaterThan(7)
      expect(v['--act-ink']).toBe('#1e1b24')
    }
  })
  it('glass over a light sky answers every question glass over a dark one does', () => {
    for (const t of TONES) expect(Object.keys(glassVars(15, 'sunny', t, 'light')).sort())
      .toEqual(Object.keys(glassVars(15, 'sunny', t)).sort())
  })
})

describe('the light token block', () => {
  const css = readFileSync('src/panel.css', 'utf8')
  const block = (sel: string) => css.slice(css.indexOf(sel + ' {'), css.indexOf('}', css.indexOf(sel + ' {')))
  const props = (b: string) => new Set([...b.matchAll(/^\s*(--[\w-]+):/gm)].map(m => m[1]))
  /* the tokens that decide what the page is drawn in: forget one and it stays drawn for a dark field */
  const PAGE = ['--bg', '--bg-2', '--ink', '--ink-2', '--muted', '--ink-lit', '--surface-rgb', '--surface',
    '--surface-hi', '--surface-press', '--edge', '--edge-hi', '--wash-rgb', '--lamp-text', '--live-text', '--danger-text']
  it('redeclares every one of them', () => {
    const dark = props(block(':root')), light = props(block(":root[data-shade='light']"))
    for (const k of PAGE) {
      expect(dark.has(k), `${k} is a :root token`).toBe(true)
      expect(light.has(k), `${k} is redeclared for light`).toBe(true)
    }
  })
  it('keeps what sits on a drawn object light in both shades', () => {
    expect(block(":root[data-shade='light']")).toMatch(/--ink-lit:\s*#f1eee8/)
  })
})
