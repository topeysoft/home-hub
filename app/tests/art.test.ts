/* The device drawings.

   art.ts states the rule at the top: what a device is made of takes the ambient, what it emits
   does not. Neither half is enforced by the type system, and the first pass of the sheet in
   design/ broke the second one in the most visible way available -- a strip labelled Off with its
   LEDs lit and a light cone under it. These tests sweep every kind against every state instead of
   trusting an eye that has already looked at the picture fifty times. */
import { describe, expect, it } from 'vitest'
import { BOX, KINDS, device, lightKind, materials, type Art, type Kind, type Mark } from '../src/art'

const DAY = 40, DUSK = -2, NIGHT = -20
const M = materials(DUSK, 'partlycloudy')
/* off, barely on, half, and full: the corners plus the middle of what a light reports */
const STATES = [
  { label: 'off', s: { on: false } },
  { label: 'on at 0.02', s: { on: true, brightness: 0.02 } },
  { label: 'on at half', s: { on: true, brightness: 0.5 } },
  { label: 'on at full', s: { on: true, brightness: 1 } },
]

/* anything that is light rather than a thing: the gradients and the two warm inks */
const EMITS = ['mPool', 'mCone', 'mGlass', '#f6dcae']
const emitting = (m: Mark) =>
  Object.values(m.at).some((v) => typeof v === 'string' && EMITS.some((e) => v.includes(e)))

/* Every mark as a bounding box. Arcs are expanded by their own radii rather than solved, so the
   box is never smaller than the truth -- a pass is a real guarantee that nothing is clipped. */
function bbox(m: Mark): [number, number, number, number] {
  const n = (k: string) => Number(m.at[k] ?? 0)
  if (m.el === 'rect') return [n('x'), n('y'), n('x') + n('width'), n('y') + n('height')]
  if (m.el === 'ellipse') return [n('cx') - n('rx'), n('cy') - n('ry'), n('cx') + n('rx'), n('cy') + n('ry')]
  if (m.el === 'circle') return [n('cx') - n('r'), n('cy') - n('r'), n('cx') + n('r'), n('cy') + n('r')]

  /* the path commands these drawings actually use: M L h v l a c, absolute and relative */
  const d = String(m.at.d)
  const box = { lo: [Infinity, Infinity], hi: [-Infinity, -Infinity] }
  const see = (px: number, py: number, pad = 0) => {
    box.lo = [Math.min(box.lo[0], px - pad), Math.min(box.lo[1], py - pad)]
    box.hi = [Math.max(box.hi[0], px + pad), Math.max(box.hi[1], py + pad)]
  }
  let x = 0, y = 0
  const tokens = d.match(/[MLHVACSQTmlhvacsqt]|-?[\d.]+/g) ?? []
  let i = 0, cmd = 'M'
  while (i < tokens.length) {
    if (/[A-Za-z]/.test(tokens[i])) { cmd = tokens[i]; i++; continue }
    const num = () => Number(tokens[i++])
    switch (cmd) {
      case 'M': x = num(); y = num(); see(x, y); break
      case 'm': x += num(); y += num(); see(x, y); break
      case 'L': x = num(); y = num(); see(x, y); break
      case 'l': x += num(); y += num(); see(x, y); break
      case 'H': x = num(); see(x, y); break
      case 'h': x += num(); see(x, y); break
      case 'V': y = num(); see(x, y); break
      case 'v': y += num(); see(x, y); break
      case 'A': case 'a': {
        const rx = num(), ry = num(); num(); num(); num()
        if (cmd === 'A') { x = num(); y = num() } else { x += num(); y += num() }
        see(x, y, Math.max(rx, ry))
        break
      }
      case 'C': case 'c': {
        for (let p = 0; p < 3; p++) {
          const px = cmd === 'C' ? num() : x + num(), py = cmd === 'C' ? num() : y + num()
          see(px, py)
          if (p === 2) { x = px; y = py }
        }
        break
      }
      default: i++
    }
  }
  return [box.lo[0], box.lo[1], box.hi[0], box.hi[1]]
}

const all = (fn: (kind: Kind, art: Art, label: string) => void) => {
  for (const kind of KINDS) for (const { label, s } of STATES) fn(kind, device(kind, s, M), `${kind} ${label}`)
}

describe('every light, in every state', () => {
  it('draws something', () => {
    all((_k, art, at) => expect(art.marks.length, at).toBeGreaterThan(3))
  })

  /* The one that matters. Off means off: no pool on the floor, no cone in the air, no lit glass,
     and no wash behind the tile. A tile that still glows is a tile that still says "on". */
  it('emits nothing at all when it is off', () => {
    for (const kind of KINDS) {
      const art = device(kind, { on: false }, M)
      expect(art.glow, `${kind} glow`).toBe(0)
      const lit = art.marks.filter(emitting)
      expect(lit.map((m) => JSON.stringify(m.at)), `${kind} emits while off`).toEqual([])
    }
  })

  it('emits more the brighter it gets', () => {
    for (const kind of KINDS) {
      const g = STATES.map(({ s }) => device(kind, s, M).glow)
      expect(g, kind).toEqual([...g].sort((a, b) => a - b))
      expect(g[0], `${kind} off`).toBe(0)
      expect(g[3], `${kind} full`).toBeGreaterThan(0)
    }
  })

  /* a light that cannot dim reports no brightness at all, and must still light up */
  it('lights up when it is on and says nothing about brightness', () => {
    for (const kind of KINDS) {
      expect(device(kind, { on: true }, M).glow, kind).toBe(device(kind, { on: true, brightness: 1 }, M).glow)
      expect(device(kind, {}, M).glow, kind).toBeGreaterThan(0)
    }
  })

  it('keeps every mark inside the box it is cropped from', () => {
    all((_k, art, at) => {
      for (const m of art.marks) {
        const [x0, y0, x1, y1] = bbox(m)
        expect(x0, `${at} ${m.el} left`).toBeGreaterThanOrEqual(0)
        expect(y0, `${at} ${m.el} top`).toBeGreaterThanOrEqual(0)
        expect(x1, `${at} ${m.el} right`).toBeLessThanOrEqual(BOX.w)
        expect(y1, `${at} ${m.el} bottom`).toBeLessThanOrEqual(BOX.h)
      }
    })
  })

  it('never leaves a fill or an opacity undefined', () => {
    all((_k, art, at) => {
      for (const m of art.marks) {
        expect(String(m.at.fill), `${at} ${m.el} fill`).not.toMatch(/undefined|NaN/)
        for (const [k, v] of Object.entries(m.at)) expect(String(v), `${at} ${m.el} ${k}`).not.toMatch(/NaN/)
      }
    })
  })
})

describe('materials', () => {
  /* the point of the ambient mix: a white shade is not the same white at noon and at midnight */
  it('moves with the sky', () => {
    expect(materials(DAY, 'sunny').matteHi).not.toBe(materials(NIGHT, 'clear-night').matteHi)
  })

  /* and the point of the limit on it: the room tints the surface, it does not repaint it */
  it('leaves a light surface lighter than a dark one at every hour', () => {
    const lum = (c: string) => { const [r, g, b] = c.match(/[\d.]+/g)!.map(Number); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
    for (const [el, cond] of [[DAY, 'sunny'], [DUSK, 'rainy'], [NIGHT, 'clear-night']] as [number, string][]) {
      const m = materials(el, cond)
      expect(lum(m.matteHi), `matte over dark at ${el}`).toBeGreaterThan(lum(m.darkLo))
      expect(lum(m.metalMid), `metal mid over lo at ${el}`).toBeGreaterThan(lum(m.metalLo))
      expect(lum(m.shadeHi), `shade hi over lo at ${el}`).toBeGreaterThan(lum(m.shadeLo))
    }
  })

  it('emitted light is the same colour whatever the sky is doing', () => {
    const pool = (el: number, c: string) => device('floor-lamp', { on: true }, materials(el, c))
      .marks.filter(emitting).map((m) => m.at.fill)
    expect(pool(DAY, 'sunny')).toEqual(pool(NIGHT, 'clear-night'))
  })
})

describe('which shape a light is', () => {
  it('reads the name a person already gave it', () => {
    expect(lightKind('Under-cabinet strip')).toBe('strip')
    expect(lightKind('Dining pendant')).toBe('pendant')
    expect(lightKind('Porch bulb')).toBe('bulb')
    expect(lightKind('Bedside lamp')).toBe('table-lamp')
    expect(lightKind('Floor lamp')).toBe('floor-lamp')
  })

  /* a guess has to have a floor: anything unrecognised is still a light on a ceiling */
  it('falls back to the one most houses have most of', () => {
    expect(lightKind('Kitchen lights')).toBe('ceiling')
    expect(lightKind('')).toBe('ceiling')
    expect(KINDS).toContain(lightKind('something nobody has ever called a light'))
  })
})
