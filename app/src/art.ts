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
  screenHi: string; screenLo: string
}

/* the base colour of each surface, before the room gets to it */
const BASE: Record<keyof Materials, RGB> = {
  metalLo: [74, 70, 64], metalMid: [179, 170, 156],
  matteHi: [242, 239, 232], matteLo: [201, 196, 184],
  darkHi: [58, 61, 68], darkLo: [21, 23, 27],
  shadeHi: [247, 230, 198], shadeLo: [224, 185, 129],
  fabricHi: [122, 116, 104], fabricLo: [78, 74, 66],
  screenHi: [42, 45, 51], screenLo: [15, 17, 20],
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
const FABRIC = 'url(#mFabric)'    // speaker cloth
const SCREEN = 'url(#mScreen)'    // a dark panel with a sheen across it

/* ---------- what a drawing is given ---------- */

/*
 * Deliberately small. A drawing gets the handful of numbers the device actually
 * reports, and everything about the picture follows from them -- which is what
 * keeps this one drawing per device rather than one per state. `brightness` is
 * 0..1; a light that cannot dim is simply 1 when it is on.
 */
export type ArtState = {
  on?: boolean
  brightness?: number     // 0..1; a light that cannot dim is simply 1 when it is on
  locked?: boolean
  position?: number       // 0..1, how far open a cover is
  live?: boolean          // a camera that is watching
  playing?: boolean
  cooling?: boolean
  heating?: boolean
}

export type Art = {
  marks: Mark[]
  /* how much of its own warm wash the tile should show behind the drawing. A lamp
     lights the room it is in, and the tile is the nearest thing to a room. */
  glow: number
  /* The device's own face, when a tile is built around it rather than beside it.
     Only the thermostat has one, and it is why: every other tile has a quiet
     corner for a drawing to be cropped into, and the climate tile has none --
     it is controls edge to edge. But it is already a dial, so the dial goes
     behind the number instead of fighting the chips for a corner. The box is in
     the same coordinates as the marks. */
  face?: { x: number; y: number; w: number; h: number }
}

export type Kind =
  | 'floor-lamp' | 'table-lamp' | 'ceiling' | 'strip' | 'bulb' | 'pendant'
  | 'camera' | 'doorbell' | 'thermostat' | 'speaker' | 'tv' | 'lock' | 'plug' | 'fan' | 'blind' | 'vacuum'
export const LIGHT_KINDS: Kind[] = ['floor-lamp', 'table-lamp', 'ceiling', 'strip', 'bulb', 'pendant']
export const KINDS: Kind[] = [...LIGHT_KINDS,
  'camera', 'doorbell', 'thermostat', 'speaker', 'tv', 'lock', 'plug', 'fan', 'blind', 'vacuum']

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


/* ---------- everything else in the house ---------- */

/*
 * None of these emit, with one exception: a smart plug's pilot light, which is
 * the only way a plug shows it is on at all. Everything else says its state with
 * shape -- a bolt across or along, slats down or up, a dish that is or is not
 * sweeping. That is the point of drawing them: a thing that looks different when
 * it is doing something does not need a word underneath saying so.
 */
function thing(kind: Kind, s: ArtState, m: Materials): Art {
  const none = { glow: 0 }

  if (kind === 'camera') {
    return {
      ...none,
      marks: [
        ell(74, 116, 30, 8, m.metalLo, { opacity: 0.5 }),
        rect(30, 30, 88, 55, MATTE, { rx: 27.5 }),
        circ(58, 58, 20, m.darkHi),
        circ(58, 58, 11.5, m.darkLo),
        /* the glint is what stops a lens reading as a hole */
        circ(53, 53, 4, '#ffffff', { opacity: s.live === false ? 0.28 : 0.55 }),
        rect(67, 85, 14, 24, PLATE, { rx: 6 }),
        ell(74, 112, 27, 8, PLATE),
      ],
    }
  }

  if (kind === 'doorbell') {
    return {
      ...none,
      marks: [
        rect(70, 10, 54, 108, DARK, { rx: 14 }),
        circ(97, 42, 16, m.darkLo),
        circ(97, 42, 9, m.darkHi),
        circ(92, 37, 3.2, '#ffffff', { opacity: 0.5 }),
        /* the live green is a signal and never takes the room, same as the lamp accent */
        circ(97, 90, 15, 'none', { stroke: '#74c69d', 'stroke-width': 2, opacity: s.live === false ? 0.2 : 0.55 }),
        circ(97, 90, 11, MATTE),
      ],
    }
  }

  if (kind === 'thermostat') {
    /* blue cooling, orange heating: the same two the panel already tints a
       climate tile with, and neither is allowed to drift with the sky */
    const arc = s.cooling ? '#7fb4e8' : s.heating ? '#e9a06a' : ''
    return {
      ...none,
      /* the bezel and nothing else: circ(96, 62, 46) with a pixel to spare, so a
         tile can put the dial round its own number and leave the base behind */
      face: { x: 49, y: 15, w: 94, h: 94 },
      marks: [
        ell(96, 122, 40, 7, m.metalLo, { opacity: 0.35 }),
        circ(96, 62, 46, PLATE),
        circ(96, 62, 39, DARK),
        circ(96, 62, 39, 'none', { stroke: m.metalMid, 'stroke-width': 1, opacity: 0.3 }),
        /* the set-point mark. The number itself stays out of the drawing: the
           tile already says it in type you can read across a room. */
        pathOf('M96 26v7', 'none', { stroke: '#f1eee8', 'stroke-width': 2, 'stroke-linecap': 'round' }),
        ...(arc ? [ell(96, 62, 43, 43, 'none', { stroke: arc, 'stroke-width': 3, opacity: 0.8, 'stroke-dasharray': '34 236', transform: 'rotate(140 96 62)' })] : []),
      ],
    }
  }

  if (kind === 'speaker') {
    return {
      ...none,
      marks: [
        ell(96, 122, 34, 7, m.metalLo, { opacity: 0.4 }),
        rect(66, 34, 60, 78, FABRIC),
        pathOf('M78 34v78M96 34v78M114 34v78', 'none', { stroke: m.fabricLo, 'stroke-width': 1, opacity: 0.45 }),
        ell(96, 112, 30, 9, m.fabricLo),
        ell(96, 34, 30, 9, PLATE),
        ell(96, 33, 19, 5.5, m.darkHi, { opacity: 0.75 }),
        ...(s.playing ? [ell(96, 33, 19, 5.5, 'none', { stroke: LAMP, 'stroke-width': 1.6, opacity: 0.7 })] : []),
      ],
    }
  }

  if (kind === 'tv') {
    return {
      ...none,
      marks: [
        ell(81, 120, 36, 6, m.metalLo, { opacity: 0.35 }),
        rect(16, 24, 130, 72, PLATE, { rx: 4 }),
        rect(19, 27, 124, 66, SCREEN, { rx: 2 }),
        /* one diagonal sheen: a dark rectangle with nothing across it reads as a
           hole cut in the tile rather than as glass */
        pathOf('M19 93L89 27h22L41 93z', '#ffffff', { opacity: s.playing ? 0.07 : 0.04 }),
        pathOf('M66 96L59 114H103L96 96Z', PLATE),
        ell(81, 117, 28, 5, m.metalLo),
      ],
    }
  }

  if (kind === 'lock') {
    /* along the door is shut, across it is open -- the one convention everybody
       already reads. Halfway between the two, which is where this started, is
       the only position that means nothing. */
    const shut = s.locked !== false
    return {
      ...none,
      marks: [
        ell(96, 66, 34, 34, m.metalLo, { opacity: 0.4 }),
        circ(94, 64, 34, PLATE),
        circ(94, 64, 26, 'none', { stroke: m.metalLo, 'stroke-width': 1.4, opacity: 0.55 }),
        rect(88, 40, 12, 48, METAL, { rx: 6, transform: shut ? 'rotate(0 94 64)' : 'rotate(90 94 64)' }),
        circ(94, 64, 5, m.darkLo, { opacity: 0.7 }),
      ],
    }
  }

  if (kind === 'plug') {
    const on = s.on === true
    return {
      glow: on ? 0.35 : 0,
      marks: [
        rect(36, 14, 108, 112, m.metalLo, { rx: 8, opacity: 0.16 }),
        rect(54, 30, 76, 80, MATTE, { rx: 18 }),
        rect(76, 50, 8, 18, m.darkLo, { rx: 4, opacity: 0.8 }),
        rect(100, 50, 8, 18, m.darkLo, { rx: 4, opacity: 0.8 }),
        rect(84, 76, 16, 9, m.darkLo, { rx: 4.5, opacity: 0.8 }),
        /* the pilot light, and the only thing on this drawing that emits */
        circ(92, 98, 3.4, on ? GLOW : m.metalLo, { opacity: on ? 1 : 0.7 }),
      ],
    }
  }

  if (kind === 'fan') {
    const spinning = s.on === true
    /* Four blades, spaced in round space and squashed afterwards, which is the
       projection of a flat disc tilted toward you. Rotating a symmetric shape
       about its OWN centre gives two blades for every one -- that is how this
       first came out with six. */
    const disc = 'translate(90 46) scale(1 0.46)'
    const blades = [24, 114, 204, 294].map((a) =>
      /* 52 and not 56: the far CORNER of a rotated blade, not its tip, is what
         reaches furthest, and at 56 it cleared the right edge of the box by
         three pixels. The box check does the trigonometry so nobody has to. */
      rect(8, -11, 52, 22, PLATE, { rx: 11, transform: `${disc} rotate(${a})` }))
    return {
      ...none,
      marks: [
        rect(24, 6, 126, 3, m.metalMid, { opacity: 0.18 }),
        ell(90, 10, 11, 3.5, PLATE),
        rect(88, 10, 4, 32, METAL),
        ell(90, 52, 17, 8, m.metalLo),
        ...blades,
        { el: 'circle', at: { cx: 0, cy: 0, r: 17, fill: PLATE, transform: disc } },
        /* the disc it sweeps, and the only thing that says it is turning */
        ...(spinning ? [ell(90, 46, 58, 26, 'none', { stroke: m.metalMid, 'stroke-width': 2, opacity: 0.2 })] : []),
      ],
    }
  }

  if (kind === 'blind') {
    /* shut is nine slats down the glass and open is none; the light below them is
       whatever is left of the window. It is NOT the lamp cone -- a window is not
       a lamp, and warming it would say the wrong thing at every hour. */
    const open = Math.max(0, Math.min(1, s.position ?? 0))
    const n = Math.round((1 - open) * 9)
    const slats = Array.from({ length: n }, (_, i) => rect(30, 10 + i * 11, 112, 7, PLATE, { rx: 2 }))
    const bottom = n ? 10 + (n - 1) * 11 + 7 : 6
    return {
      ...none,
      marks: [
        rect(26, 6, 120, 104, m.darkLo, { rx: 3, opacity: 0.55 }),
        ...(bottom < 110 ? [rect(32, bottom, 108, 110 - bottom, m.matteLo, { opacity: 0.45 })] : []),
        ...slats,
        rect(26, 6, 120, 104, 'none', { rx: 3, stroke: m.metalMid, 'stroke-width': 2, opacity: 0.45 }),
        rect(22, 110, 128, 5, PLATE, { rx: 1.5 }),
      ],
    }
  }

  /* vacuum */
  const cleaning = s.on === true
  return {
    ...none,
    marks: [
      ell(92, 110, 50, 12, m.metalLo, { opacity: 0.34 }),
      /* thickness the same way as everything else: the same dish, twice, offset */
      ell(92, 86, 50, 28, m.metalLo),
      ell(92, 78, 50, 28, MATTE),
      ell(92, 70, 16, 9, DARK),
      ell(92, 68, 16, 9, PLATE),
      ...(cleaning ? [ell(92, 82, 58, 33, 'none', { stroke: m.metalMid, 'stroke-width': 2, opacity: 0.2 })] : []),
    ],
  }
}

/* ---------- the way in ---------- */

export function device(kind: Kind, s: ArtState, m: Materials): Art {
  return (LIGHT_KINDS as string[]).includes(kind) ? light(kind, s, m) : thing(kind, s, m)
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
/*
 * What a device gets drawn as, given what the hub knows about it.
 *
 * null is a real answer and the important one: a sensor, a motion detector and a
 * door contact get no drawing. They are read rather than operated, they have no
 * agreed shape, and inventing one would put a picture of a thing next to a number
 * that is the actual point of the tile. They stay on rung four, which is where
 * the ladder in *When there is no artwork* always said most things would live.
 */
export function kindFor(capability: string, name: string): Kind | null {
  switch (capability) {
    case 'light': return lightKind(name)
    case 'lock': return 'lock'
    case 'switch': return 'plug'
    case 'fan': return 'fan'
    case 'cover': return 'blind'
    case 'vacuum': return 'vacuum'
    case 'climate': return 'thermostat'
    /* a doorbell is a camera to the hub, and nothing like one on a wall */
    case 'camera': return /\b(doorbell|door ?bell|bell)\b/i.test(name) ? 'doorbell' : 'camera'
    case 'media': return /\b(tv|television|screen|display|roku|chromecast|shield|apple ?tv|projector)\b/i.test(name) ? 'tv' : 'speaker'
    default: return null
  }
}

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
