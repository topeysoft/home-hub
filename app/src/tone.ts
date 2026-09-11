/*
 * What colour a card is, given what the sky is doing.
 *
 * The rule that matters: a card is never given an absolute colour. It is given a
 * distance from the sky — always this much lighter, always this far around the
 * hue wheel. Fixed colours look right at one hour and wrong at another, because
 * the field moves a long way between them: the band behind the cards sits at
 * L 0.15 at midnight and L 0.49 at noon. A card fixed at L 0.30 is a lit surface
 * at night and a hole punched in the daylight by lunchtime. Holding the distance
 * instead means the relationship can never invert.
 *
 * Two things follow from that on their own, and neither is special-cased:
 * cards dim through a storm, because the sky they track has dimmed; and their
 * colour strengthens under overcast, because a flat grey sky can carry colour
 * that a bright blue one drowns.
 *
 * What does NOT move: the lamp accent, the live green, the danger red. Those are
 * signals — "on", "watching", "unlocked" — and a signal that changes colour with
 * the weather is not a signal. They stay exactly as panel.css declares them.
 */

import { clamp, ground, oklch } from './sky'

export type ToneName = 'warm' | 'cool' | 'pastel' | 'follow'

/* The surfaces that take a tone, and the hue each one leans to. Deliberately
   short: a media tile is coloured by its artwork and a thermostat by --tint
   (blue cooling, orange heating), so neither is listed — a card that already
   means something with its colour does not get overpainted. Hues are absolute:
   warmth is a place on the wheel, not a relationship, and deriving it from the
   sky turns "warm" pink under a violet night. */
const WARM_HUES = { light: 76, lock: 66 }
const COOL_HUES = { light: 210, lock: 245 }

export type Cap = keyof typeof WARM_HUES

type Tone = { dL: number; C: number; hues: Record<Cap, number> }

const WARM: Tone = { dL: 0.135, C: 0.050, hues: WARM_HUES }
const COOL: Tone = { dL: 0.135, C: 0.058, hues: COOL_HUES }
const PASTEL: Tone = { dL: 0.335, C: 0.058, hues: { ...COOL_HUES, light: 82 } }

/* 'follow' is the only tone that changes character rather than just lightness:
   cool and open while the sun is up, lamplit and low once it is down. */
function toneOf(name: ToneName, day: boolean): Tone {
  if (name === 'warm') return WARM
  if (name === 'cool') return COOL
  if (name === 'pastel') return PASTEL
  return day ? PASTEL : WARM
}

/* the point past which a card has out-lightened its own text and the ink must flip */
const INK_FLIPS_AT = 0.62

export type ToneVars = Record<string, string>

/*
 * The CSS custom properties the panel paints with, for one moment of one day.
 * Returned as a plain object so the shell can bind it as a style and every card
 * inherits; nothing has to know the sky to be coloured by it.
 */
export function toneVars(elevation: number, condition: string, name: ToneName = 'follow'): ToneVars {
  const field = oklch(ground(elevation, condition))
  const day = elevation > 3                                   // the sun is up, not merely lightening the horizon
  const tone = toneOf(name, day)

  // a colourful sky needs quieter cards; a near-grey one can take the full chroma
  const C = tone.C * (1 - 0.35 * Math.min(field.C / 0.09, 1))
  const L = clamp(field.L + tone.dL, 0.16, 0.92)
  const light = L > INK_FLIPS_AT

  const vars: ToneVars = {
    '--card-l': L.toFixed(3),
    '--card-c': C.toFixed(3),
    // ink, and everything that has to sit legibly on a card, follows the card
    '--card-ink': light ? '#1e1b24' : '#f1eee8',
    '--card-ink-2': light ? 'rgba(30,27,36,.62)' : '#b9b5ad',
    '--card-edge': light ? 'rgba(30,27,36,.14)' : 'rgba(255,255,255,.10)',
    '--card-hi': light ? 'rgba(30,27,36,.10)' : 'rgba(255,255,255,.07)',
    '--card-press': light ? 'rgba(30,27,36,.17)' : 'rgba(255,255,255,.13)',
    '--card-track': light ? 'rgba(30,27,36,.18)' : 'rgba(255,255,255,.18)',
    // the lamp still has to read as lamplight against a card that may now be pale
    '--card-lamp-ink': light ? '#7a4a10' : '#e9b872',
  }
  /* what an opened device lends the room: its own hue, at the strength a tint
     can carry without fighting the sky it sits on */
  vars['--tint-light'] = `oklch(0.62 ${(C * 2.4).toFixed(3)} ${tone.hues.light} / .34)`
  vars['--tint-lock'] = `oklch(0.62 ${(C * 2.4).toFixed(3)} ${tone.hues.lock} / .30)`

  const card = (hue: number, c = C) =>
    `linear-gradient(155deg, oklch(${(L + 0.055).toFixed(3)} ${c.toFixed(3)} ${hue}), oklch(${L.toFixed(3)} ${c.toFixed(3)} ${hue + 6}))`

  for (const [cap, hue] of Object.entries(tone.hues)) vars[`--card-${cap}`] = card(hue)
  // a room, a sensor, anything without a capability of its own: the same surface,
  // near enough neutral that the coloured cards stay the ones you notice
  vars['--card-plain'] = card(tone.hues.lock, C * 0.22)
  return vars
}

/* remembered per house, not per screen: everyone sees the tone the house is set to */
export const TONES: { id: ToneName; label: string; hint: string }[] = [
  { id: 'follow', label: 'Follow the light', hint: 'Cool and open by day, lamplit after sunset.' },
  { id: 'warm', label: 'Warm', hint: 'Lamplight, at every hour.' },
  { id: 'cool', label: 'Cool', hint: 'Blues and greens, at every hour.' },
  { id: 'pastel', label: 'Pastel', hint: 'Light and open. Best in a sunny room.' },
]

export function isTone(v: unknown): v is ToneName {
  return v === 'warm' || v === 'cool' || v === 'pastel' || v === 'follow'
}
