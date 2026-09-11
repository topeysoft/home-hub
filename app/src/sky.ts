/*
 * What the sky is made of, in one place.
 *
 * Sky.vue draws it and tone.ts colours the interface from it. Both read these
 * tables, so the picture and the palette cannot drift apart: add a condition
 * here and the sky, the weather illustration and the tiles all learn it at once.
 */

export type RGB = [number, number, number]
export type Wx = { clouds: number; rain: number; snow: number; fog: number; lightning: boolean; wind: number }

/* palette keyframes by sun elevation: [top, middle, horizon] */
export const KEYS: [number, RGB[]][] = [
  [-18, [[4, 5, 10], [7, 9, 16], [12, 14, 26]]],
  [-9, [[6, 7, 16], [14, 16, 34], [44, 32, 56]]],
  [-3, [[10, 14, 34], [38, 34, 74], [158, 84, 60]]],
  [0, [[14, 24, 52], [56, 62, 106], [220, 134, 74]]],
  [6, [[18, 40, 80], [54, 98, 142], [222, 170, 108]]],
  [15, [[22, 60, 108], [58, 124, 174], [184, 184, 172]]],
  [40, [[26, 78, 136], [70, 148, 202], [170, 200, 218]]],
  [90, [[26, 78, 136], [70, 148, 202], [170, 200, 218]]],
]

export const COND: Record<string, Partial<Wx>> = {
  sunny: { clouds: .06 }, 'clear-night': { clouds: .06 }, partlycloudy: { clouds: .42 }, cloudy: { clouds: .9 },
  fog: { clouds: .5, fog: 1 }, rainy: { clouds: .9, rain: .6 }, pouring: { clouds: 1, rain: 1 }, hail: { clouds: 1, rain: .8 },
  lightning: { clouds: 1, lightning: true }, 'lightning-rainy': { clouds: 1, rain: .8, lightning: true },
  snowy: { clouds: .9, snow: .7 }, 'snowy-rainy': { clouds: 1, snow: .5, rain: .4 }, windy: { clouds: .3, wind: 3 }, 'windy-variant': { clouds: .7, wind: 3 },
  exceptional: { clouds: .5 },
}
export const wxOf = (c: string): Wx => ({ clouds: 0, rain: 0, snow: 0, fog: 0, lightning: false, wind: 1, ...COND[c] })

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
export const mix = (a: RGB, b: RGB, t: number): RGB => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]
export const rgb = (c: RGB, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`
export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))

export function palette(el: number, wx: Wx): RGB[] {
  let i = 0; while (i < KEYS.length - 2 && el > KEYS[i + 1][0]) i++
  const [e0, a] = KEYS[i], [e1, b] = KEYS[i + 1]
  const t = clamp((el - e0) / (e1 - e0))
  return a.map((c, k) => {
    let out = mix(c, b[k], t)
    out = mix(out, [58, 64, 72], wx.clouds * .55)             // overcast greys the sky
    out = mix(out, [22, 24, 30], wx.rain * .3)                // rain darkens it
    out = mix(out, [116, 122, 128], wx.fog * .3)              // fog flattens it
    return out
  })
}

/* the veil that keeps the interface readable, sampled where the cards sit (panel.css .sky-veil) */
const VEIL: RGB = [12, 13, 16]
const VEIL_A = 0.52

/* what a card is actually laid over: the sky's middle band, seen through the veil */
export function ground(el: number, condition: string): RGB {
  const [, band] = palette(el, wxOf(condition))
  return mix(band, VEIL, VEIL_A)
}

export type Oklch = { L: number; C: number; H: number }

/* sRGB -> OKLCH. Lightness here is perceptual, which is the whole point: it is
   what lets a tile hold the same apparent distance from a sky that moves. */
export function oklch([r, g, b]: RGB): Oklch {
  const f = (c: number) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4))
  const R = f(r / 255), G = f(g / 255), B = f(b / 255)
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B)
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B)
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B)
  const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
  const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
  const Bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
  let H = Math.atan2(Bb, A) * 180 / Math.PI
  if (H < 0) H += 360
  return { L, C: Math.hypot(A, Bb), H }
}
