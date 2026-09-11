/* The device drawings.

   art.ts states the rule at the top: what a device is made of takes the ambient, what it emits
   does not. Neither half is enforced by the type system, and the first pass of the sheet in
   design/ broke the second one in the most visible way available -- a strip labelled Off with its
   LEDs lit and a light cone under it. These tests sweep every kind against every state instead of
   trusting an eye that has already looked at the picture fifty times. */
import { describe, expect, it } from 'vitest'
import { BOX, KINDS, LIGHT_KINDS, device, lightKind, materials, type ArtState, type Kind, type Mark } from '../src/art'

const DAY = 40, DUSK = -2, NIGHT = -20
const M = materials(DUSK, 'partlycloudy')

/* off, barely on, half, and full: the corners plus the middle of what a light reports */
const LIT_STATES: { label: string; s: ArtState }[] = [
  { label: 'off', s: { on: false } },
  { label: 'on at 0.02', s: { on: true, brightness: 0.02 } },
  { label: 'on at half', s: { on: true, brightness: 0.5 } },
  { label: 'on at full', s: { on: true, brightness: 1 } },
]

/* everything a non-light can be told, including saying nothing at all */
const THING_STATES: { label: string; s: ArtState }[] = [
  { label: 'nothing said', s: {} },
  { label: 'off', s: { on: false } },
  { label: 'on', s: { on: true } },
  { label: 'locked', s: { locked: true } },
  { label: 'unlocked', s: { locked: false } },
  { label: 'shut', s: { position: 0 } },
  { label: 'half open', s: { position: 0.5 } },
  { label: 'open', s: { position: 1 } },
  { label: 'watching', s: { live: true } },
  { label: 'not watching', s: { live: false } },
  { label: 'playing', s: { playing: true } },
  { label: 'cooling', s: { cooling: true } },
  { label: 'heating', s: { heating: true } },
]

const statesFor = (k: Kind) => (LIGHT_KINDS.includes(k) ? LIT_STATES : THING_STATES)

/* anything that is light rather than a thing: the emitting gradients and the two warm inks */
const EMITS = ['mPool', 'mCone', 'mGlass', '#f6dcae']
const emitting = (m: Mark) =>
  Object.values(m.at).some((v) => typeof v === 'string' && EMITS.some((e) => v.includes(e)))

/* ---------- boxes ---------- */

/* A 2D matrix, so a transformed mark can be checked where it actually lands rather than where it
   was written. The fan's blades are the reason: each is authored around the origin at y-11 and
   only the transform puts it on the hub, so a test that ignored transforms would either fail on a
   correct drawing or -- worse -- pass one that hung off the edge. */
type Mat = [number, number, number, number, number, number]
const I: Mat = [1, 0, 0, 1, 0, 0]
const mul = (a: Mat, b: Mat): Mat => [
  a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
  a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
  a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5],
]
function parseTransform(t: string): Mat {
  let m = I
  for (const [, name, args] of t.matchAll(/(\w+)\(([^)]*)\)/g)) {
    const n = args.trim().split(/[\s,]+/).map(Number)
    if (name === 'translate') m = mul(m, [1, 0, 0, 1, n[0], n[1] ?? 0])
    else if (name === 'scale') m = mul(m, [n[0], 0, 0, n[1] ?? n[0], 0, 0])
    else if (name === 'rotate') {
      const r = (n[0] * Math.PI) / 180, c = Math.cos(r), s = Math.sin(r)
      const rot: Mat = [c, s, -s, c, 0, 0]
      m = n.length > 1
        ? mul(mul(mul(m, [1, 0, 0, 1, n[1], n[2]]), rot), [1, 0, 0, 1, -n[1], -n[2]])
        : mul(m, rot)
    } else throw new Error(`the box check does not know the transform ${name}()`)
  }
  return m
}

/* Every mark as a bounding box. Arcs are expanded by their own radii rather than solved, so the
   box is never smaller than the truth -- a pass is a real guarantee that nothing is clipped. */
function bbox(m: Mark): [number, number, number, number] {
  const n = (k: string) => Number(m.at[k] ?? 0)
  let lo: [number, number], hi: [number, number]

  if (m.el === 'rect') { lo = [n('x'), n('y')]; hi = [n('x') + n('width'), n('y') + n('height')] }
  else if (m.el === 'ellipse') { lo = [n('cx') - n('rx'), n('cy') - n('ry')]; hi = [n('cx') + n('rx'), n('cy') + n('ry')] }
  else if (m.el === 'circle') { lo = [n('cx') - n('r'), n('cy') - n('r')]; hi = [n('cx') + n('r'), n('cy') + n('r')] }
  else {
    /* the path commands these drawings actually use: M L H V l h v a c, absolute and relative */
    const d = String(m.at.d)
    const box = { lo: [Infinity, Infinity], hi: [-Infinity, -Infinity] }
    const see = (px: number, py: number, pad = 0) => {
      box.lo = [Math.min(box.lo[0], px - pad), Math.min(box.lo[1], py - pad)]
      box.hi = [Math.max(box.hi[0], px + pad), Math.max(box.hi[1], py + pad)]
    }
    let x = 0, y = 0
    const tokens = d.match(/[MLHVACSQTmlhvacsqtzZ]|-?[\d.]+/g) ?? []
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
    lo = box.lo as [number, number]; hi = box.hi as [number, number]
  }

  if (!m.at.transform) return [lo[0], lo[1], hi[0], hi[1]]
  const t = parseTransform(String(m.at.transform))
  const at = (x: number, y: number) => [t[0] * x + t[2] * y + t[4], t[1] * x + t[3] * y + t[5]]

  /* An ellipse under a matrix is still an ellipse, and its extents are exact -- rotating the
     four corners of its box instead would inflate a circle by its diagonal and fail a drawing
     that fits perfectly well. Rects and paths do want the corners. */
  if (m.el === 'ellipse' || m.el === 'circle') {
    const rx = (hi[0] - lo[0]) / 2, ry = (hi[1] - lo[1]) / 2
    const [cx, cy] = at((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
    const hw = Math.hypot(t[0] * rx, t[2] * ry), hh = Math.hypot(t[1] * rx, t[3] * ry)
    return [cx - hw, cy - hh, cx + hw, cy + hh]
  }

  const corners = [at(lo[0], lo[1]), at(hi[0], lo[1]), at(lo[0], hi[1]), at(hi[0], hi[1])]
  return [
    Math.min(...corners.map((c) => c[0])), Math.min(...corners.map((c) => c[1])),
    Math.max(...corners.map((c) => c[0])), Math.max(...corners.map((c) => c[1])),
  ]
}

const sweep = (fn: (kind: Kind, art: ReturnType<typeof device>, at: string) => void) => {
  for (const kind of KINDS) for (const { label, s } of statesFor(kind)) fn(kind, device(kind, s, M), `${kind} ${label}`)
}

/* ---------- every device ---------- */

describe('every device, in every state', () => {
  it('draws something', () => {
    sweep((_k, art, at) => expect(art.marks.length, at).toBeGreaterThan(3))
  })

  /* The one that matters, and the reason this file exists. Told it is off, nothing may emit: no
     pool on the floor, no cone in the air, no lit glass, no pilot light and no wash behind the
     tile. A tile that still glows is a tile that still says "on". */
  it('emits nothing at all when it is told it is off', () => {
    for (const kind of KINDS) {
      const art = device(kind, { on: false }, M)
      expect(art.glow, `${kind} glow`).toBe(0)
      expect(art.marks.filter(emitting).map((m) => JSON.stringify(m.at)), `${kind} emits while off`).toEqual([])
    }
  })

  it('keeps every mark inside the box it is cropped from', () => {
    sweep((_k, art, at) => {
      for (const m of art.marks) {
        const [x0, y0, x1, y1] = bbox(m)
        expect(x0, `${at} ${m.el} left`).toBeGreaterThanOrEqual(0)
        expect(y0, `${at} ${m.el} top`).toBeGreaterThanOrEqual(0)
        expect(x1, `${at} ${m.el} right`).toBeLessThanOrEqual(BOX.w)
        expect(y1, `${at} ${m.el} bottom`).toBeLessThanOrEqual(BOX.h)
      }
    })
  })

  it('never leaves a fill or a number undefined', () => {
    sweep((_k, art, at) => {
      for (const m of art.marks) {
        expect(String(m.at.fill), `${at} ${m.el} fill`).not.toMatch(/undefined|NaN/)
        for (const [k, v] of Object.entries(m.at)) expect(String(v), `${at} ${m.el} ${k}`).not.toMatch(/NaN|undefined/)
      }
    })
  })

  /* a drawing that looks the same whatever it is told is a drawing that is not saying anything */
  it('looks different when the thing is doing something', () => {
    const busy: Partial<Record<Kind, ArtState>> = {
      camera: { live: true }, doorbell: { live: true }, thermostat: { cooling: true },
      speaker: { playing: true }, tv: { playing: true }, lock: { locked: false },
      plug: { on: true }, fan: { on: true }, blind: { position: 1 }, vacuum: { on: true },
    }
    for (const kind of KINDS) {
      const idle = LIGHT_KINDS.includes(kind) ? { on: false } : { on: false, live: false, locked: true, position: 0 }
      const on = LIGHT_KINDS.includes(kind) ? { on: true, brightness: 1 } : busy[kind]!
      expect(JSON.stringify(device(kind, on, M)), kind).not.toBe(JSON.stringify(device(kind, idle, M)))
    }
  })
})

/* ---------- lights, which are the ones that emit ---------- */

describe('every light', () => {
  it('emits more the brighter it gets', () => {
    for (const kind of LIGHT_KINDS) {
      const g = LIT_STATES.map(({ s }) => device(kind, s, M).glow)
      expect(g, kind).toEqual([...g].sort((a, b) => a - b))
      expect(g[0], `${kind} off`).toBe(0)
      expect(g[3], `${kind} full`).toBeGreaterThan(0)
    }
  })

  /* a light that cannot dim reports no brightness at all, and must still light up */
  it('lights up when it is on and says nothing about brightness', () => {
    for (const kind of LIGHT_KINDS) {
      expect(device(kind, { on: true }, M).glow, kind).toBe(device(kind, { on: true, brightness: 1 }, M).glow)
      expect(device(kind, {}, M).glow, kind).toBeGreaterThan(0)
    }
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
    expect(LIGHT_KINDS).toContain(lightKind('something nobody has ever called a light'))
  })
})
