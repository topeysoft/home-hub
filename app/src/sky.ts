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

/* ---------- the weather illustration ---------- */
/*
 * The picture beside the greeting, as numbers. It lives here rather than in RailView.vue for the
 * reason at the top of this file: the canvas behind the panel and the drawing in front of it must
 * agree, and the only way to guarantee that is to have them read the same lines. See
 * design/Weather.dc.html, which mock/weather-sheet.mjs draws from this file: it is generated, not
 * kept in step by hand, and CI fails the build if it falls behind.
 *
 * Night is not a condition -- there is none in COND, and Home Assistant does not report one. The
 * house says what the weather is; the sun says which light it is in. So every condition has to
 * hold up twice, and `nightness` is what carries it between the two.
 */

/* How far into the night we are: 0 while the sun is still up, 1 once it is well down. A ramp
   rather than a switch, because the sky behind this drawing crossfades and a picture that snapped
   would arrive at the wrong moment. It opens at the elevation the rail already treated as night. */
export const nightness = (el: number) => clamp((3 - el) / 9)

/* How much of the starfield gets through -- thinned by cloud, snuffed by fog. Lifted from Sky.vue's
   own `starA` so the stars in the drawing and the stars on the canvas come and go together. */
export const starAlpha = (el: number, wx: Wx) =>
  clamp((-el - 3) / 8) * (1 - wx.clouds * 0.9) * (1 - wx.fog * 0.8)

const SUN: RGB = [246, 220, 168]
const MOON: RGB = [223, 228, 238]
/* what the cloud is made of at each end of its range: thin and bright, thick and grey */
const BODY: [RGB, RGB][] = [[[255, 255, 255], [195, 201, 212]], [[216, 220, 230], [154, 161, 173]], [[154, 163, 180], [109, 116, 128]]]
const MOONLIT: RGB = [66, 74, 96]
/* precipitation keeps its shape and loses its light; each is [by day, by night] */
const RAIN: [RGB, RGB] = [[159, 195, 232], [110, 140, 176]]
const SNOW: [RGB, RGB] = [[230, 236, 245], [185, 194, 207]]
const FOG: [RGB, RGB] = [[170, 178, 189], [117, 124, 134]]
const GUST: [RGB, RGB] = [[207, 214, 226], [133, 141, 155]]

export type Illustration = {
  cloud: { fill: [string, string, string]; opacity: number; transform: string }
  sun: { col: string; opacity: number }
  moon: { col: string; opacity: number; biteX: number }
  stars: { d: string; opacity: number }
  rain: { d: string; col: string; opacity: number }
  snow: { d: string; col: string; opacity: number }
  fog: { d: string; col: string; opacity: number }
  wind: { d: string; col: string; opacity: number }
  bolt: { d: string; opacity: number }
}

/* a drop, a flake, a fog bar, a star -- each a path string, so no loops run inside the SVG */
const dot = (x: number, y: number, r: number) => `M${x} ${y} m${-r} 0 a${r} ${r} 0 1 0 ${2 * r} 0 a${r} ${r} 0 1 0 ${-2 * r} 0 `
const path = (n: number, x0: number, gap: number, at: (x: number, i: number) => string) =>
  Array.from({ length: n }, (_, i) => at(x0 + i * gap, i)).join('')
const BARS = 'M22 112h58 M96 112h92 M40 132h64 M118 132h54'
const GUSTS = 'M18 60h58a13 13 0 1 0-13-13 M18 84h84a13 13 0 1 1-13 13'
/* the bolt sits clear of the bottom edge: it used to run to y158 in a 150-tall box and lose its tail */
const BOLT = 'M112 86 L86 122 h20 l-6 24 26-36 h-20 z'
/* the same handful of stars every time, so the same weather is always the same picture */
const STARS = [[24, 28, 1.7], [46, 15, 1.2], [70, 34, 1.5], [32, 54, 1.3], [100, 18, 1.9], [176, 16, 1.4],
               [194, 46, 1.6], [18, 74, 1.2], [186, 82, 1.5], [148, 10, 1.3], [122, 40, 1.1], [60, 70, 1.4]]
const FIELD = STARS.map(([x, y, r]) => dot(x, y, r)).join('')

export function illustration(el: number, condition: string): Illustration {
  const wx = wxOf(condition)
  const night = nightness(el)
  const cover = wx.clouds
  /* the cloud greys and swells as cover thickens, and by night the moon is the only light on it --
     but a thin wisp still catches that light, so only a full deck goes to a dark mass */
  const thick = clamp((cover - 0.35) / 0.65)
  const lit = 0.44 + thick * 0.32
  const scale = 0.66 + cover * 0.34
  const shows = 0.25 + (1 - Math.min(1, cover / 0.55)) * 0.75       // how much of the disc is still out
  const body = BODY.map(([a, b], i) => rgb(mix(mix(a, b, thick), MOONLIT, (lit + i * 0.04) * night))) as [string, string, string]
  const wet = (c: [RGB, RGB]) => rgb(mix(c[0], c[1], night))

  return {
    cloud: {
      fill: body,
      /* a trace of cloud on a clear sky, not none -- at night it needs more of itself to read as a
         wisp rather than as a hole punched in the stars */
      opacity: cover < 0.1 ? lerp(0.34, 0.55, night) : 1,
      transform: `translate(${(105 * (1 - scale)).toFixed(1)} ${(100 * (1 - scale)).toFixed(1)}) scale(${scale.toFixed(3)})`,
    },
    /* sun and moon are two discs in the same place, crossfading, exactly as they overlap on the
       canvas through twilight. The bite is what makes the moon a moon. Cloud hides whichever is
       up, but never entirely -- a disc behind a deck is still a bright patch. */
    sun: { col: rgb(SUN), opacity: shows * (1 - night) },
    moon: { col: rgb(MOON), opacity: shows * night, biteX: 138 },
    stars: { d: FIELD, opacity: starAlpha(el, wx) },
    rain: { d: wx.rain ? path(Math.round(2 + wx.rain * 3), 62, 26, (x) => `M${x} 118 l-7 22 `) : '', col: wet(RAIN), opacity: wx.rain ? 0.45 + wx.rain * 0.55 : 0 },
    snow: { d: wx.snow ? path(Math.round(2 + wx.snow * 3), 66, 26, (x, i) => dot(x, 124 + (i % 2) * 12, 5)) : '', col: wet(SNOW), opacity: wx.snow ? 0.5 + wx.snow * 0.5 : 0 },
    fog: { d: wx.fog ? BARS : '', col: wet(FOG), opacity: wx.fog * 0.72 },
    wind: { d: wx.wind > 1.5 ? GUSTS : '', col: wet(GUST), opacity: wx.wind > 1.5 ? lerp(0.72, 0.6, night) : 0 },
    bolt: { d: wx.lightning ? BOLT : '', opacity: wx.lightning ? 1 : 0 },
  }
}
