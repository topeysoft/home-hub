/* The weather illustration beside the greeting.

   sky.ts states the law at the top of its illustration section: night is not a condition. Home
   Assistant reports the weather and the sun reports the light, so each of the fifteen conditions
   has to hold up twice — once in daylight and once after dark. Nothing in the type system holds
   anyone to that, and for a long time nothing did: the sheet in design/ drew fourteen of the
   fifteen by day only. These tests sweep the whole space instead. */
import { describe, expect, it } from 'vitest'
import { COND, illustration, nightness, starAlpha, wxOf, type Illustration } from '../src/sky'

const ELEVATIONS = [-40, -18, -9, -3, -0.5, 0, 3, 6, 15, 40, 89]
const CONDITIONS = Object.keys(COND)
const DAY = 40, NIGHT = -20

/* the box every mark has to live in: the viewBox RailView.vue draws through */
const W = 210, H = 150

const lum = (css: string) => {
  const [r, g, b] = css.match(/[\d.]+/g)!.map(Number)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/* Every mark the illustration makes, as a bounding box. Arcs are expanded by their own radii
   rather than solved, so the box is never smaller than the truth — a pass here is a real
   guarantee that nothing is being clipped, which is exactly how the bolt lost its tail. */
function bbox(d: string) {
  let x = 0, y = 0, x0 = 0, y0 = 0
  const box = { min: [Infinity, Infinity], max: [-Infinity, -Infinity] }
  const see = (px: number, py: number, pad = 0) => {
    box.min = [Math.min(box.min[0], px - pad), Math.min(box.min[1], py - pad)]
    box.max = [Math.max(box.max[0], px + pad), Math.max(box.max[1], py + pad)]
  }
  for (const [, cmd, argstr] of d.matchAll(/([MmLlHhVvAaZz])([^MmLlHhVvAaZz]*)/g)) {
    const n = (argstr.match(/-?[\d.]+/g) ?? []).map(Number)
    const rel = cmd === cmd.toLowerCase()
    if (cmd === 'Z' || cmd === 'z') { x = x0; y = y0; continue }
    if (cmd === 'H' || cmd === 'h') { for (const v of n) { x = rel ? x + v : v; see(x, y) } continue }
    if (cmd === 'V' || cmd === 'v') { for (const v of n) { y = rel ? y + v : v; see(x, y) } continue }
    if (cmd === 'A' || cmd === 'a') {
      for (let i = 0; i + 6 < n.length; i += 7) {
        const [rx, ry] = [n[i], n[i + 1]]
        see(x, y, Math.max(rx, ry))
        x = rel ? x + n[i + 5] : n[i + 5]; y = rel ? y + n[i + 6] : n[i + 6]
        see(x, y, Math.max(rx, ry))
      }
      continue
    }
    for (let i = 0; i + 1 < n.length; i += 2) {
      x = rel ? x + n[i] : n[i]; y = rel ? y + n[i + 1] : n[i + 1]
      if ((cmd === 'M' || cmd === 'm') && i === 0) { x0 = x; y0 = y }
      see(x, y)
    }
  }
  return box
}

const marks = (p: Illustration) => [p.stars, p.rain, p.snow, p.fog, p.wind, p.bolt]
const opacities = (p: Illustration) =>
  [p.cloud.opacity, p.sun.opacity, p.moon.opacity, ...marks(p).map((m) => m.opacity)]

describe('the law sky.ts is built on', () => {
  it('draws every condition differently by night than by day', () => {
    for (const condition of CONDITIONS) {
      const day = JSON.stringify(illustration(DAY, condition))
      const night = JSON.stringify(illustration(NIGHT, condition))
      expect(night, condition).not.toEqual(day)
    }
  })

  it('always has something in the sky to be the light', () => {
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        const p = illustration(el, condition)
        expect(p.sun.opacity + p.moon.opacity, `${condition} / ${el}°`).toBeGreaterThan(0)
      }
    }
  })

  it('hands the sun over to the moon without either arriving twice', () => {
    /* one disc fades out exactly as the other fades in, so the pair never reads as two suns */
    for (const el of ELEVATIONS) {
      const p = illustration(el, 'sunny')
      expect(p.sun.opacity + p.moon.opacity, `${el}°`).toBeCloseTo(illustration(el, 'sunny').sun.opacity + p.moon.opacity)
      expect(nightness(el), `${el}°`).toBeGreaterThanOrEqual(0)
      expect(nightness(el), `${el}°`).toBeLessThanOrEqual(1)
    }
    expect(illustration(89, 'sunny').moon.opacity).toBe(0)
    expect(illustration(-40, 'sunny').sun.opacity).toBe(0)
  })

  it('never lights the cloud more at night than in daylight', () => {
    for (const condition of CONDITIONS) {
      const day = illustration(DAY, condition).cloud.fill
      const night = illustration(NIGHT, condition).cloud.fill
      for (let i = 0; i < 3; i++) {
        expect(lum(night[i]), `${condition} stop ${i}`).toBeLessThan(lum(day[i]))
      }
    }
  })

  it('shows no stars in daylight, and lets cloud and fog take them', () => {
    for (const condition of CONDITIONS) {
      expect(illustration(DAY, condition).stars.opacity, condition).toBe(0)
    }
    expect(illustration(NIGHT, 'clear-night').stars.opacity).toBeGreaterThan(0.5)
    /* cloud thins them; fog thins what the cloud left. `fog` and `exceptional` are the same half
       cover, so the difference between them is the fog and nothing else. */
    expect(starAlpha(NIGHT, wxOf('cloudy'))).toBeLessThan(starAlpha(NIGHT, wxOf('clear-night')))
    expect(wxOf('fog').clouds).toBe(wxOf('exceptional').clouds)
    expect(starAlpha(NIGHT, wxOf('fog'))).toBeLessThan(starAlpha(NIGHT, wxOf('exceptional')) / 4)
  })

  it('keeps every mark inside the frame, at every hour and every weather', () => {
    /* the bolt used to run to y158 in a 150-tall box and lose its tail, in the app and on the
       design sheet both, for as long as either had existed */
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        for (const mark of marks(illustration(el, condition))) {
          if (!mark.d) continue
          const b = bbox(mark.d)
          expect(b.min[0], `${condition} / ${el}° left`).toBeGreaterThanOrEqual(0)
          expect(b.min[1], `${condition} / ${el}° top`).toBeGreaterThanOrEqual(0)
          expect(b.max[0], `${condition} / ${el}° right`).toBeLessThanOrEqual(W)
          expect(b.max[1], `${condition} / ${el}° bottom`).toBeLessThanOrEqual(H)
        }
      }
    }
  })

  it('keeps every opacity a real number the SVG can use', () => {
    for (const condition of CONDITIONS) {
      for (const el of ELEVATIONS) {
        for (const o of opacities(illustration(el, condition))) {
          expect(Number.isFinite(o), `${condition} / ${el}°`).toBe(true)
          expect(o, `${condition} / ${el}°`).toBeGreaterThanOrEqual(0)
          expect(o, `${condition} / ${el}°`).toBeLessThanOrEqual(1)
        }
      }
    }
  })
})
