/*
 * What a device looks like, in one place.
 *
 * The same argument as the weather illustration in sky.ts, applied to the things
 * in the house: the tiles draw these marks and design/Devices.dc.html is drawn
 * from the same numbers, so the sheet and the panel cannot drift apart. Add a
 * kind here and both learn it at once.
 *
 * Rung two of *When there is no artwork*. The ladder there is unchanged and this
 * is only its second step: a device that brings its own picture (a camera frame,
 * album art) still wins, and anything with no drawing here still falls through to
 * the icon, oversized and faint. Most houses will mostly see that last rung, so
 * nothing in this file is allowed to make it look like a hole.
 *
 * THE RULE, and it is the only one that matters: what a device is MADE OF takes
 * the ambient; what it EMITS does not. A white shade goes cool at midday and
 * creamy at dusk, because that is what a white thing in a room does. Mix the
 * light it throws the same way and a lamp turns blue at noon -- and a tile that
 * has stopped looking warm has stopped meaning "on". Emitted light sits with the
 * lamp accent, the live green and the danger red: signals, and a signal that
 * changes colour is not a signal.
 */

import { ground, mix, rgb, type RGB } from './sky'

/* Every drawing is composed in this box and cropped into the corner of a tile,
   the way the reference renders already are. Fixed, because the marks below are
   literal coordinates and a second box would mean a second set of them. */
export const BOX = { w: 150, h: 130 }

/* ---------- materials ---------- */

/*
 * The panel paints these into one set of gradient defs and every mark refers to
 * them by name, so a tile carries no colour of its own. Two stops make a plate,
 * three make a cylinder; that is the whole vocabulary.
 */
export type Materials = {
  metalLo: string; metalMid: string
  matteHi: string; matteLo: string
  darkHi: string; darkLo: string
  shadeHi: string; shadeLo: string
  fabricHi: string; fabricLo: string
}

/* the base colour of each surface, before the room gets to it */
const BASE: Record<keyof Materials, RGB> = {
  metalLo: [74, 70, 64], metalMid: [179, 170, 156],
  matteHi: [242, 239, 232], matteLo: [201, 196, 184],
  darkHi: [58, 61, 68], darkLo: [21, 23, 27],
  shadeHi: [247, 230, 198], shadeLo: [224, 185, 129],
  fabricHi: [122, 116, 104], fabricLo: [78, 74, 66],
}

/* How far a surface takes the colour of the room it stands in. Gentle on
   purpose: at 0 the shelf looks like stickers pasted on the sky, and past about
   a third every device turns the same colour as every other and the library
   stops being a library. */
const AMBIENT = 0.22

export function materials(el: number, condition: string): Materials {
  const room = ground(el, condition)
  const out = {} as Materials
  for (const k of Object.keys(BASE) as (keyof Materials)[]) out[k] = rgb(mix(BASE[k], room, AMBIENT))
  return out
}

/* Emitted light, which does NOT take the room -- see the rule at the top. These
   are the same values panel.css declares for the lamp accent. */
export const LIT = '#fbeed6'        // the surface a lamp's own light falls on
export const GLOW = '#f6dcae'       // the light itself, close in
export const LAMP = '#e9b872'       // the accent, and the far edge of a light pool

/* ---------- marks ---------- */

/*
 * A mark is one SVG element and its attributes, nothing more. The tile does
 * `<component :is="m.el" v-bind="m.at" />` and knows nothing about lamps; all the
 * drawing lives here, where it can be tested without a browser.
 */
export type Mark = { el: 'rect' | 'ellipse' | 'circle' | 'path'; at: Record<string, string | number> }

type Extra = Record<string, string | number>
const rect = (x: number, y: number, w: number, h: number, fill: string, extra: Extra = {}): Mark =>
  ({ el: 'rect', at: { x, y, width: w, height: h, fill, ...extra } })
const ell = (cx: number, cy: number, rx: number, ry: number, fill: string, extra: Extra = {}): Mark =>
  ({ el: 'ellipse', at: { cx, cy, rx, ry, fill, ...extra } })
const circ = (cx: number, cy: number, r: number, fill: string, extra: Extra = {}): Mark =>
  ({ el: 'circle', at: { cx, cy, r, fill, ...extra } })
const pathOf = (d: string, fill: string, extra: Extra = {}): Mark =>
  ({ el: 'path', at: { d, fill, ...extra } })

/* the gradients the panel declares; naming them here keeps the tile dumb */
const METAL = 'url(#mMetal)'      // a cylinder: dark, light, dark
const PLATE = 'url(#mPlate)'      // a flat metal face
const MATTE = 'url(#mMatte)'      // painted or plastic, unlit
const SHADE = 'url(#mShade)'      // a lampshade with light behind it
const DARK = 'url(#mDark)'        // dark plastic
const POOL = 'url(#mPool)'        // light landing on a floor
const CONE = 'url(#mCone)'        // light on its way down
const GLASS = 'url(#mGlass)'      // a lit bulb

/* ---------- what a drawing is given ---------- */

/*
 * Deliberately small. A drawing gets the handful of numbers the device actually
 * reports, and everything about the picture follows from them -- which is what
 * keeps this one drawing per device rather than one per state. `brightness` is
 * 0..1; a light that cannot dim is simply 1 when it is on.
 */
export type ArtState = { on?: boolean; brightness?: number }

export type Art = {
  marks: Mark[]
  /* how much of its own warm wash the tile should show behind the drawing. A lamp
     lights the room it is in, and the tile is the nearest thing to a room. */
  glow: number
}

export type Kind = 'floor-lamp' | 'table-lamp' | 'ceiling' | 'strip' | 'bulb' | 'pendant'
export const KINDS: Kind[] = ['floor-lamp', 'table-lamp', 'ceiling', 'strip', 'bulb', 'pendant']

/* How much light is coming out, 0..1. Off is off: no pool, no cone, no glow, no
   exceptions. An "off" tile that still emits was a real bug on the first pass of
   the sheet -- the strip said Off and its LEDs were lit -- and art.test.ts now
   holds every kind to it. */
const output = (s: ArtState) => (s.on === false ? 0 : Math.max(0, Math.min(1, s.brightness ?? 1)))

/* ---------- the lights ---------- */

/*
 * A house is mostly lights, and a light is not one shape: the difference between
 * a floor lamp and a ceiling fitting is the whole reason this is a library and
 * not a single "light" drawing scaled up and down.
 */
function light(kind: Kind, s: ArtState, m: Materials): Art {
  const k = output(s)
  const on = k > 0
  const glow = on ? 0.25 + k * 0.75 : 0

  if (kind === 'floor-lamp') {
    return {
      glow,
      marks: [
        ...(on ? [ell(96, 104, 30 + k * 24, 13 + k * 12, POOL, { opacity: +(0.22 + k * 0.78).toFixed(3) })] : []),
        rect(94, 42, 5, 70, METAL, { rx: 2.5 }),
        pathOf('M72 42h49l-9-30h-31z', on ? SHADE : m.matteLo),
        ell(96.5, 42, 24.5, 5, LIT, { opacity: on ? +(0.34 + k * 0.58).toFixed(3) : 0.12 }),
        ...(on ? [ell(96.5, 45, 18, 3.5, GLOW, { opacity: +(0.3 + k * 0.25).toFixed(3) })] : []),
        /* thickness is two ellipses offset, here and everywhere else */
        ell(96, 115, 23, 6, m.metalLo),
        ell(96, 112, 23, 6, m.metalMid),
      ],
    }
  }

  if (kind === 'table-lamp') {
    return {
      glow,
      marks: [
        ...(on ? [ell(92, 98, 28 + k * 22, 11 + k * 10, POOL, { opacity: +(0.22 + k * 0.78).toFixed(3) })] : []),
        /* the surface it stands on, which is what separates it from a floor lamp
           at a glance more than its height does */
        rect(18, 106, 132, 2, m.metalMid, { opacity: 0.16 }),
        rect(89.5, 56, 5, 38, METAL, { rx: 2.5 }),
        ell(92, 98, 26, 7, m.metalLo),
        ell(92, 95, 26, 7, m.metalMid),
        /* a drum, not a cone: straight sides are the difference */
        pathOf('M66 24h52v32H66z', on ? SHADE : m.matteLo),
        ell(92, 24, 26, 6, on ? m.shadeHi : m.matteHi),
        ell(92, 56, 26, 6, LIT, { opacity: on ? +(0.32 + k * 0.58).toFixed(3) : 0.12 }),
        ...(on ? [ell(92, 58, 18, 4, GLOW, { opacity: +(0.26 + k * 0.24).toFixed(3) })] : []),
      ],
    }
  }

  if (kind === 'ceiling') {
    return {
      glow,
      marks: [
        ...(on ? [pathOf('M70 30L46 130h100L118 30z', CONE, { opacity: +(0.3 + k * 0.7).toFixed(3) })] : []),
        /* the ceiling it is fixed to: without it this reads as a bowl on a shelf */
        rect(26, 8, 124, 3, m.metalMid, { opacity: 0.18 }),
        rect(88, 11, 10, 8, PLATE),
        pathOf('M67 30a26 22 0 0 1 52 0z', MATTE),
        ell(93, 30, 26, 5, LIT, { opacity: on ? +(0.4 + k * 0.55).toFixed(3) : 0.12 }),
        ...(on ? [ell(93, 32, 17, 3, GLOW, { opacity: +(0.34 + k * 0.26).toFixed(3) })] : []),
      ],
    }
  }

  if (kind === 'strip') {
    /* five emitters, and when the strip is off they are dark plastic like
       everything else on it -- not dimmed warm, which still reads as lit */
    const dots = [40, 62, 84, 106, 128].map((x) =>
      rect(x, 49, 12, 2.6, on ? GLOW : m.metalLo, { rx: 1.3, opacity: on ? +(0.45 + k * 0.5).toFixed(3) : 0.85 }))
    return {
      glow,
      marks: [
        ...(on ? [pathOf('M34 53L14 126h122L128 53z', CONE, { opacity: +(0.22 + k * 0.5).toFixed(3) })] : []),
        rect(20, 40, 130, 7, PLATE, { rx: 1.5 }),
        rect(32, 47, 112, 6, DARK, { rx: 3 }),
        ...dots,
      ],
    }
  }

  if (kind === 'bulb') {
    return {
      glow,
      marks: [
        ...(on ? [ell(98, 58, 52, 50, POOL, { opacity: +(0.3 + k * 0.5).toFixed(3) })] : []),
        rect(97, 0, 2.4, 24, m.metalLo),
        rect(89, 24, 18, 13, PLATE, { rx: 2 }),
        /* the screw thread, two lines: enough to say "bulb" at tile size */
        rect(89, 27, 18, 1.4, m.metalLo, { opacity: 0.7 }),
        rect(89, 31, 18, 1.4, m.metalLo, { opacity: 0.7 }),
        circ(98, 60, 25, on ? GLASS : m.matteLo, { opacity: on ? 1 : 0.5 }),
        pathOf('M92 45v9a6 6 0 0 0 12 0v-9', 'none',
          { stroke: on ? LIT : m.metalLo, 'stroke-width': 2, 'stroke-linecap': 'round', opacity: on ? 1 : 0.6 }),
      ],
    }
  }

  /* pendant */
  return {
    glow,
    marks: [
      ...(on ? [pathOf('M68 64L50 130h92L124 64z', CONE, { opacity: +(0.3 + k * 0.7).toFixed(3) })] : []),
      /* it hangs from something, and saying so is most of what makes it a
         pendant rather than a cone floating in the tile */
      rect(24, 6, 126, 3, m.metalMid, { opacity: 0.18 }),
      ell(96, 9, 10, 3.5, PLATE),
      rect(95, 9, 2.4, 23, m.metalLo),
      /* painted metal, where the ceiling fitting is matte: the two hang
         differently and they should not read as the same object */
      pathOf('M68 64h56l-17-32H85z', PLATE),
      ell(96, 64, 28, 6, LIT, { opacity: on ? +(0.38 + k * 0.54).toFixed(3) : 0.12 }),
      ...(on ? [ell(96, 66, 19, 4, GLOW, { opacity: +(0.3 + k * 0.25).toFixed(3) })] : []),
    ],
  }
}

/* ---------- the way in ---------- */

export function device(kind: Kind, s: ArtState, m: Materials): Art {
  return light(kind, s, m)
}

/*
 * Which shape a light is.
 *
 * A guess, and it is worth being honest that it is one: Home Assistant reports a
 * light, never a floor lamp, so until a device can be told what it looks like
 * this reads the name a person already gave it. Getting it wrong costs little --
 * every branch is still a light, still lights up, still dims -- but it is a
 * placeholder for a proper per-device setting, not the answer.
 */
const BY_NAME: [RegExp, Kind][] = [
  [/\b(strip|under[- ]?cabinet|led|cove|shelf)\b/i, 'strip'],
  [/\b(pendant|hanging)\b/i, 'pendant'],
  [/\b(bulb|porch|outside|outdoor|garage)\b/i, 'bulb'],
  [/\b(bedside|desk|table|side)\b/i, 'table-lamp'],
  [/\b(floor|standing|corner|torch)\b/i, 'floor-lamp'],
  [/\b(lamp)\b/i, 'floor-lamp'],
]

export function lightKind(name: string): Kind {
  for (const [re, kind] of BY_NAME) if (re.test(name)) return kind
  /* most lights in most houses are on the ceiling, so that is the safe default */
  return 'ceiling'
}
