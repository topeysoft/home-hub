// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What color a household can ask a light to be.
 *
 * The panel could already SHOW a bulb's color and not change it, so the only way
 * to make a lamp pink was Home Assistant's own screens -- the one thing the box
 * is not supposed to need. This is the vocabulary for the other half.
 *
 * Three answers, and the order matters because it is the order somebody meets
 * them in. AUTOMATIC, which is where every light starts and what most of them
 * stay on. A SWATCH, for the person who wants the lamp green tonight. And the
 * two columns behind "More colors", for the thirteenth color -- the one that is
 * not in the twelve, and the one that IS but does not look like it on the actual
 * bulb, which is the harder case and the reason tuning exists at all. A lamp's
 * idea of pink is not the swatch's pink; rendering varies by make, by model, by
 * how warm the phosphor has gone. A preset is an instruction, not a result.
 *
 * See design/device page 4.
 */
import { clamp, type RGB } from './sky'

/*
 * A light's color, as the house holds it. `auto` is not a color and that is the
 * point: it is the absence of one, which has to be a state somebody can choose
 * and choose again rather than the accident of whatever the bulb was last left
 * at. Everything else names what gets sent.
 */
export type Wanted =
  | { kind: 'auto' }
  | { kind: 'white'; kelvin: number }
  | { kind: 'color'; hue: number; amount: number }      // hue 0-360, amount 0-100, as HA's hs_color

/* ---------- the twelve ---------- */

/*
 * Eight colors, evenly round the wheel at one chroma so that no swatch is louder
 * than its neighbor and the row reads as a set rather than a ranking. Written as
 * hue and amount rather than as hex because that is what gets SENT -- HA takes
 * hs_color directly, so there is no conversion between what the grid shows and
 * what the lamp is asked for, and nothing to drift.
 *
 * The amounts are not all 100. A bulb at full saturation in the blues and greens
 * is a color a room cannot really be lit by; these are the strengths at which a
 * lamp still lights something, which is what a lamp is for.
 */
export const COLORS: { hue: number; amount: number }[] = [
  { hue: 350, amount: 72 },   // rose
  { hue: 22, amount: 84 },    // coral
  { hue: 48, amount: 92 },    // amber
  { hue: 96, amount: 66 },    // leaf
  { hue: 152, amount: 62 },   // green
  { hue: 202, amount: 68 },   // sky
  { hue: 258, amount: 58 },   // violet
  { hue: 302, amount: 66 },   // magenta
]

/*
 * And the whites, which live in the same grid as the colors on purpose. The
 * Warmth column used to hold these and it DISAPPEARED the moment a bulb went
 * into a color mode -- `v-if="warmth != null"`, because a bulb in hs mode
 * reports no color_temp_kelvin. That is Home Assistant's mode system showing
 * through a panel whose whole job is to hide it: set a lamp pink and the way
 * back to white vanished with the control. Here white is a swatch beside pink,
 * so there are no modes, nothing appears or disappears, and the way back is in
 * the same place it always was.
 *
 * The four are the ones a domestic bulb actually spans, and the ends are the
 * ends LightPane already used.
 */
export const WHITES = [2200, 2700, 4000, 6500]

/* ---------- turning one into pixels ---------- */

/*
 * hs to sRGB, for drawing a swatch, a track and the readout. Value is pinned at
 * 1: hs_color says nothing about how bright the lamp is -- brightness is its own
 * control and its own column -- so a swatch shows the color at full output and
 * the dimmer says how much of it there is.
 */
export function hsRgb(hue: number, amount: number): RGB {
  const h = ((hue % 360) + 360) % 360 / 60
  const s = Math.min(1, Math.max(0, amount / 100))
  const f = h - Math.floor(h)
  const [p, q, t] = [1 - s, 1 - s * f, 1 - s * (1 - f)]
  const i = Math.floor(h) % 6
  const c: RGB = [[1, t, p], [q, 1, p], [p, 1, t], [p, q, 1], [t, p, 1], [1, p, q]][i] as RGB
  return [Math.round(c[0] * 255), Math.round(c[1] * 255), Math.round(c[2] * 255)]
}

/*
 * A color temperature as the eye sees it, for the white swatches and the lamp's
 * own drawing. Not a physical black-body curve: an approximation good enough to
 * tell 2200K from 6500K at a glance, which is all a swatch has to do. Clamped to
 * the range a bulb offers so the two ends are the two ends.
 */
const WHITE_STOPS: [number, RGB][] = [
  [2000, [255, 157, 63]], [2700, [255, 200, 140]], [4000, [255, 231, 208]], [6500, [223, 235, 255]],
]
export function kelvinRgb(k: number): RGB {
  /* Anchored on what each one LOOKS like rather than fitted to a black-body
     curve. Linear across the whole range put 2200K and 2700K within a few units
     of each other, and two of the four whites were the same circle. */
  const t = Math.min(6500, Math.max(2000, k))
  let i = 0
  while (i < WHITE_STOPS.length - 2 && t > WHITE_STOPS[i + 1][0]) i++
  const [k0, c0] = WHITE_STOPS[i], [k1, c1] = WHITE_STOPS[i + 1]
  const f = (t - k0) / (k1 - k0)
  return [0, 1, 2].map(j => Math.round(c0[j] + (c1[j] - c0[j]) * f)) as RGB
}

/*
 * A SWATCH, which is not the same thing as the color.
 *
 * hsRgb draws a color the way a lamp emits it, at full output, and eight of those
 * side by side are eight neon discs -- the yellows shout and the blues sink, and
 * the row reads as a ranking rather than as a set. A swatch is a label for a
 * color, not a sample of it, so it is drawn at one lightness across the wheel.
 *
 * That the label and the lamp do not match exactly is not a flaw to be fixed; it
 * is the fact the whole of More colors exists for. A bulb's idea of pink is not
 * the swatch's pink whatever either of them is drawn at, which is why the tuning
 * columns show what the LAMP is showing and tell you to match it against the
 * room. Anything on this panel standing for the actual light -- a tile, the tune
 * preview, the amount track -- uses the real sRGB and not this.
 */
export const swatchCss = (hue: number, amount: number) =>
  `hsl(${Math.round(hue)} ${Math.round(Math.min(96, amount))}% 62%)`

/* What a wanted color looks like, whatever kind it is. Automatic has no color of
   its own -- it is whatever the house has the lamp at -- so it is drawn from the
   white the hour would give, which is what Automatic means. */
export function wantedRgb(w: Wanted, autoKelvin = 2700): RGB {
  return w.kind === 'color' ? hsRgb(w.hue, w.amount)
    : w.kind === 'white' ? kelvinRgb(w.kelvin)
    : kelvinRgb(autoKelvin)
}

/*
 * What Automatic MEANS at a given moment: cool and open while the sun is up,
 * lamplight once it is down. The same sentence the tone already uses for itself
 * -- "Follow the light" is `follow`'s own label -- and the same input, because a
 * lamp and a card disagreeing about what hour it is would be worse than either
 * being wrong alone.
 *
 * The ends are the ones a domestic bulb actually spans and LightPane already
 * used. What is deliberately NOT here is anything about the room: a lamp on
 * Automatic follows the sky, not the scene, because a scene that wants a color
 * says so and pins one.
 */
export function autoKelvin(elevation: number): number {
  const t = clamp((elevation + 6) / 18)            // 0 well after dark, 1 around midday
  return Math.round(2200 + t * (4300 - 2200))
}

/* ---------- reading the lamp, and telling it ---------- */

/*
 * Which of the three a light is currently on, off the attributes the hub sends.
 *
 * `pinned` is the house's own record: a light nobody has ever set is on Automatic
 * and stays there, which is how a house out of the box warms after sunset with
 * nobody having asked. Without that flag this would have to guess from the bulb's
 * state, and a bulb sitting at 2700K cannot be told apart from one somebody
 * deliberately set to 2700K -- the difference is who decided, and only the house
 * knows that.
 */
export function wantedOf(attrs: Record<string, any> | null | undefined): Wanted {
  const a = attrs ?? {}
  if (!a.color_pinned) return { kind: 'auto' }
  const hs = a.hs_color
  if (Array.isArray(hs) && hs.length >= 2 && typeof hs[0] === 'number' && typeof hs[1] === 'number' && hs[1] > 0)
    return { kind: 'color', hue: hs[0], amount: hs[1] }
  if (typeof a.color_temp_kelvin === 'number') return { kind: 'white', kelvin: a.color_temp_kelvin }
  return { kind: 'auto' }
}

/* Where the two columns start when the pane opens: what the lamp is showing now,
   so the first thing a finger does is a nudge rather than a jump. A lamp with no
   color of its own opens in the middle of the wheel at a gentle amount, which is
   somewhere to start rather than a claim about the bulb. */
export function handlesOf(w: Wanted): { hue: number; amount: number } {
  return w.kind === 'color' ? { hue: w.hue, amount: w.amount } : { hue: 32, amount: 60 }
}

/*
 * What gets sent. One shape for all three, so the caller never assembles service
 * data by hand and a new kind cannot forget a field.
 *
 * Automatic sends the white the house would have chosen anyway and clears the
 * pin, so the lamp does not sit on yesterday's color waiting for the next thing
 * to happen: choosing Automatic is a change you can see, not just a record.
 */
export function dataFor(w: Wanted, autoKelvin = 2700): Record<string, unknown> {
  /* `color_pinned` is not a service parameter and the hub takes it off before calling
     the driver -- it is the house's own record of whether anybody chose this, which
     is the one thing a bulb cannot be asked. api.py/act. */
  const pin = { color_pinned: w.kind !== 'auto' }
  if (w.kind === 'color') return { ...pin, hs_color: [Math.round(w.hue), Math.round(w.amount)] }
  return { ...pin, color_temp_kelvin: Math.round(w.kind === 'white' ? w.kelvin : autoKelvin) }
}

/* and what the panel should believe before the house answers, so a tap lands on
   the card at once rather than after a round trip */
export function guessFor(w: Wanted, autoKelvin = 2700): Record<string, any> {
  const base = { color_pinned: w.kind !== 'auto' }
  if (w.kind === 'color')
    return { ...base, hs_color: [w.hue, w.amount], rgb_color: hsRgb(w.hue, w.amount), color_mode: 'hs', color_temp_kelvin: null }
  const k = w.kind === 'white' ? w.kelvin : autoKelvin
  return { ...base, color_temp_kelvin: k, rgb_color: kelvinRgb(k), color_mode: 'color_temp', hs_color: null }
}

/*
 * Whether two wants are the same, for deciding which swatch wears the ring.
 * Loose on the numbers on purpose: a lamp reports back what it actually managed,
 * which is rarely the exact hue it was asked for, and a swatch that stops looking
 * chosen the moment the bulb answers is worse than one that is a degree out.
 */
export function same(a: Wanted, b: Wanted): boolean {
  if (a.kind !== b.kind) return false
  if (a.kind === 'white' && b.kind === 'white') return Math.abs(a.kelvin - b.kelvin) <= 150
  if (a.kind === 'color' && b.kind === 'color') {
    /* round the wheel, where 358 and 2 are four degrees apart and not 356 */
    const diff = Math.abs(a.hue - b.hue) % 360
    return Math.min(diff, 360 - diff) <= 8 && Math.abs(a.amount - b.amount) <= 8
  }
  return true
}
