/* What colour a card is, given what the sky is doing.

   tone.ts states its own law at the top of the file: a card is never given an absolute colour, only
   a distance from the sky, so the relationship can never invert. Nothing in the type system holds
   anyone to that. These tests do — they sweep the whole day, every condition and every tone, and
   check the law still holds at each step. */
import { describe, expect, it } from 'vitest'
import { COND, ground, oklch } from '../src/sky'
import { glassVars, isTone, TONES, toneVars, type ToneName } from '../src/tone'

const ELEVATIONS = [-40, -18, -9, -3, -0.5, 0, 3, 6, 15, 40, 89]
const CONDITIONS = Object.keys(COND)
const NAMES: ToneName[] = ['warm', 'cool', 'pastel', 'follow']

const L = (vars: Record<string, string>) => Number(vars['--card-l'])
const C = (vars: Record<string, string>) => Number(vars['--card-c'])

describe('the law the file is built on', () => {
  it('never lets a card fall to or below the sky it sits on, at any hour or weather', () => {
    for (const name of NAMES) {
      for (const condition of CONDITIONS) {
        for (const el of ELEVATIONS) {
          const field = oklch(ground(el, condition))
          const card = L(toneVars(el, condition, name))
          expect(card, `${name} / ${condition} / ${el}°`).toBeGreaterThan(field.L)
        }
      }
    }
  })

  it('holds roughly the same distance from the sky rather than a fixed colour', () => {
    // Midnight and midday are a long way apart. A card that tracked nothing would sit at one value
    // for both; a card that tracks the sky moves with it and keeps its distance.
    const night = toneVars(-30, 'clear-night', 'warm')
    const noon = toneVars(45, 'sunny', 'warm')
    expect(L(noon)).toBeGreaterThan(L(night))

    const gapNight = L(night) - oklch(ground(-30, 'clear-night')).L
    const gapNoon = L(noon) - oklch(ground(45, 'sunny')).L
    expect(Math.abs(gapNight - gapNoon)).toBeLessThan(0.02)
  })

  it('dims the cards through a storm, because the sky they track has dimmed', () => {
    expect(L(toneVars(20, 'pouring'))).toBeLessThan(L(toneVars(20, 'sunny')))
  })

  it('lets colour strengthen under a flat grey sky that can carry it', () => {
    expect(C(toneVars(20, 'cloudy'))).toBeGreaterThan(C(toneVars(20, 'sunny')))
  })
})

describe('text that has to stay readable on the card', () => {
  it('flips the ink to dark once the card is lighter than the ink it was carrying', () => {
    for (const name of NAMES) {
      for (const condition of CONDITIONS) {
        for (const el of ELEVATIONS) {
          const vars = toneVars(el, condition, name)
          const dark = vars['--card-ink'] === '#1e1b24'
          expect(dark, `${name} / ${condition} / ${el}°`).toBe(L(vars) > 0.62)
        }
      }
    }
  })

  it('moves everything that sits on a card together, never half of it', () => {
    for (const el of [-30, 45]) {
      const vars = toneVars(el, 'sunny')
      const light = L(vars) > 0.62
      for (const key of ['--card-ink', '--card-ink-2', '--card-edge', '--card-hi', '--card-press', '--card-track', '--card-lamp-ink']) {
        expect(vars[key], `${key} at ${el}°`).toBeTruthy()
      }
      expect(vars['--card-lamp-ink']).toBe(light ? '#7a4a10' : '#e9b872')
    }
  })
})

describe('the tones a house can pick', () => {
  it('gives every surface a colour, whichever tone is chosen', () => {
    for (const name of NAMES) {
      const vars = toneVars(10, 'sunny', name)
      for (const key of ['--card-light', '--card-lock', '--card-plain', '--tint-light', '--tint-lock']) {
        expect(vars[key], `${name} ${key}`).toMatch(/^(oklch|linear-gradient)\(/)
      }
    }
  })

  it('keeps a plain card quieter than one that means something', () => {
    // A room card must not compete with a lamp that is on.
    const vars = toneVars(10, 'sunny', 'warm')
    expect(vars['--card-plain']).not.toBe(vars['--card-light'])
  })

  it('follows the light: open by day, lamplit after sunset', () => {
    expect(toneVars(30, 'sunny', 'follow')['--card-light']).toBe(toneVars(30, 'sunny', 'pastel')['--card-light'])
    expect(toneVars(-10, 'clear-night', 'follow')['--card-light']).toBe(toneVars(-10, 'clear-night', 'warm')['--card-light'])
  })

  it('stays inside a range that is neither black nor white', () => {
    for (const name of NAMES) {
      for (const condition of CONDITIONS) {
        for (const el of ELEVATIONS) {
          const l = L(toneVars(el, condition, name))
          expect(l, `${name} / ${condition} / ${el}°`).toBeGreaterThanOrEqual(0.16)
          expect(l, `${name} / ${condition} / ${el}°`).toBeLessThanOrEqual(0.92)
        }
      }
    }
  })

  it('never emits something CSS cannot read', () => {
    for (const [k, v] of Object.entries(toneVars(10, 'sunny'))) {
      expect(v, k).not.toContain('NaN')
      expect(v, k).not.toContain('undefined')
    }
  })
})

describe('picking a tone', () => {
  it('accepts the ones that exist and refuses anything else', () => {
    for (const t of TONES) expect(isTone(t.id)).toBe(true)
    for (const bad of ['neon', '', null, undefined, 0, {}]) expect(isTone(bad)).toBe(false)
  })

  it('names every tone and says what it is for', () => {
    for (const t of TONES) {
      expect(t.label.trim()).toBeTruthy()
      expect(t.hint.trim()).toBeTruthy()
    }
    expect(new Set(TONES.map(t => t.id)).size).toBe(TONES.length)
  })

  it('offers a tone for every one the code can actually make', () => {
    expect(new Set(TONES.map(t => t.id))).toEqual(new Set(NAMES))
  })
})

describe('an unknown weather condition', () => {
  it('still produces a usable card rather than NaN', () => {
    const vars = toneVars(10, 'meteor-shower')
    expect(Number.isFinite(L(vars))).toBe(true)
    expect(vars['--card-ink']).toBeTruthy()
  })
})

/* The other face. Same law, one extra clause: a pane's EDGE has to swap ends across the day, or
   the pane stops reading as glass somewhere around mid-morning. */
describe('the pane, at every hour', () => {
  const alphas = (rim: string) => rim.match(/[\d.]+(?=\))/g)!.map(Number)

  it('never lets a pane fall to or below the sky it sits on', () => {
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        const field = oklch(ground(el, condition))
        const pane = Number(glassVars(el, condition)['--glass'].match(/oklch\(([\d.]+)/)![1])
        expect(pane, `${condition} / ${el}°`).toBeGreaterThan(field.L)
      }
    }
  })

  it('moves the edge from a catch on top to a shadow at the foot as the day lightens', () => {
    const night = alphas(glassVars(-18, 'clear-night')['--glass-rim'])
    const noon = alphas(glassVars(40, 'sunny')['--glass-rim'])
    expect(night[0]).toBeGreaterThan(noon[0])       // the catch fades out
    expect(night[2]).toBeLessThan(noon[2])          // the shadow comes in
  })

  it('takes the saturation off what is behind it as the sky brightens', () => {
    expect(Number(glassVars(40, 'sunny')['--glass-sat']))
      .toBeLessThan(Number(glassVars(-18, 'clear-night')['--glass-sat']))
  })

  /* The room a pane is in front of. Paper blurs it; glass cannot, because the blur the pane is made
     of has nothing left to work on -- so the room is taken down by a scrim instead, and how far down
     is the one thing here that goes UP as the day does. */
  it('takes a bright room down further than a dark one, to sit a pane in front of either', () => {
    const alpha = (c: string) => Number(c.match(/[\d.]+(?=\))/)![0])
    expect(alpha(glassVars(40, 'sunny')['--glass-scrim']))
      .toBeGreaterThan(alpha(glassVars(-18, 'clear-night')['--glass-scrim']))
  })

  it('never dims the room so far that what you came from stops being there', () => {
    const alpha = (c: string) => Number(c.match(/[\d.]+(?=\))/)![0])
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        const a = alpha(glassVars(el, condition)['--glass-scrim'])
        expect(a, `${condition} / ${el}°`).toBeGreaterThan(0.3)
        expect(a, `${condition} / ${el}°`).toBeLessThan(0.75)
      }
    }
  })

  /* A pane is measured against the ROOM, not the sky: by the time you are looking at one, the sky is
     not what is behind it -- the scrim is. */
  it('paints a pane against the dimmed room in front of it rather than the open sky', () => {
    const foot = (v: string) => Number(v.match(/oklch\(([\d.]+)[^)]*\)\)$/)![1])
    expect(foot(glassVars(40, 'sunny')['--pane']))
      .toBeGreaterThan(foot(glassVars(-18, 'clear-night')['--pane']))
  })

  /* The other half of the same move. A card gets this from toneVars; a pane is translucent over a
     room that gets bright, so paper's fixed greys came off the screen at 2.0:1 on it at noon. */
  it('lifts the ink on a pane as the room behind it brightens, and never below what paper gives', () => {
    const L = (v: string) => Number(v.match(/oklch\(([\d.]+)/)![1])
    expect(L(glassVars(40, 'sunny')['--pane-muted']))
      .toBeGreaterThan(L(glassVars(-18, 'clear-night')['--pane-muted']))
    expect(L(glassVars(40, 'sunny')['--pane-ink-2']))
      .toBeGreaterThanOrEqual(L(glassVars(-18, 'clear-night')['--pane-ink-2']))

    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        const v = glassVars(el, condition)
        expect(L(v['--pane-muted']), `muted / ${condition} / ${el}°`).toBeGreaterThanOrEqual(0.58)
        expect(L(v['--pane-ink-2']), `ink-2 / ${condition} / ${el}°`).toBeGreaterThanOrEqual(0.76)
        expect(L(v['--pane-ink-2']), `ink-2 under muted / ${condition} / ${el}°`)
          .toBeGreaterThan(L(v['--pane-muted']))
      }
    }
  })

  /* The floor: the same face on a host that cannot paint a backdrop-filter. Not a second palette --
     each stop is the colour its translucent twin composites to, so the only thing lost is depth. */
  it('gives the flat face no transparency to fall through', () => {
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        const v = glassVars(el, condition)
        for (const k of ['--glass-flat', '--pane-flat']) {
          // an oklch() with a slash in it carries an alpha, and an unblurred card with an alpha is
          // the thing this exists to avoid: .34 of a colour over the open sky is hardly a card
          expect(v[k], `${k} / ${condition} / ${el}°`).not.toMatch(/\//)
          expect(v[k]).toMatch(/^linear-gradient\(/)
        }
      }
    }
  })

  it('tracks the sky flattened exactly as it does through the lens', () => {
    const first = (v: string) => Number(v.match(/oklch\(([\d.]+)/)![1])
    for (const k of [['--glass', '--glass-flat'], ['--pane', '--pane-flat']] as const) {
      const nightLens = first(glassVars(-18, 'clear-night')[k[0]])
      const noonLens = first(glassVars(40, 'sunny')[k[0]])
      const nightFlat = first(glassVars(-18, 'clear-night')[k[1]])
      const noonFlat = first(glassVars(40, 'sunny')[k[1]])
      expect(noonLens - nightLens, `${k[0]} does not move across the day`).toBeGreaterThan(0.05)
      expect(noonFlat - nightFlat, `${k[1]} does not move with it`).toBeGreaterThan(0.05)
    }
  })

  it('gives every property a value, at every hour and weather', () => {
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        const v = glassVars(el, condition)
        for (const k of ['--glass', '--glass-sweep', '--glass-rim', '--glass-inner', '--glass-drop', '--glass-sat', '--glass-br', '--glass-field', '--glass-scrim', '--glass-blur',
          '--pane', '--pane-edge', '--pane-ink-2', '--pane-muted', '--pane-blur',
          '--glass-flat', '--pane-flat']) {
          expect(v[k], `${k} / ${condition} / ${el}°`).toBeTruthy()
          expect(v[k]).not.toContain('NaN')
        }
      }
    }
  })
})
