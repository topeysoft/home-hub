// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What a strip controller says about a light, and the roofline it may be part of, as the wall draws them.
 *
 * The strip controller (docs/strip.md item 51) tells the hub why a strip is dark when it is, and the
 * brain turns that into words (brain/hub/controller.py) and hangs them on the light, under `strip`.
 * design/controller-panel/, "held", decided A with B's row on 1 October: a strip held dark says
 * Staying off on its tile with the reason under it, the room gets a Why?, a tap opens the light's pane
 * rather than a switch that cannot work, and Needs a look carries a row for it to Home. Every word is
 * the brain's; this file only decides where each one goes, and what a preview shows when there is no
 * controller in the room to be held (?held=supply|range|trips|wiring, ?roofline=..., AGENTS.md §4).
 */
import type { Device, Held, Room, Roofline, Strip, StripRow, Yard } from './api'

/** The light's report, when the controller is holding it dark. Nothing for one that is merely lit
 *  a little less: running hot and holding under 5 A change nothing on the tile. */
export const heldOf = (d?: Device | null): Held | null =>
  (d?.attrs?.strip?.held ? (d.attrs.strip as Held) : null)

/** The one muted line on the pane for a light lit a little less than asked, or nothing. */
export const quietOf = (d?: Device | null): string | null => d?.attrs?.strip?.quiet ?? null

/** The tile's second line: the reason, as a sentence that starts the line (InRoomA.dc.html draws
 *  "It's on a different power supply" under Staying off). */
export function heldLine(h: Held): string {
  switch (h.held) {
    case 'supply': return 'It’s on a different power supply'
    case 'range': return 'It’s on the wrong kind of power supply'
    case 'trips': return 'It kept cutting out'
    case 'wiring': return 'A wire is in the wrong place'
    default: return ''
  }
}

/** The light in this room the room's chip is about: the first one held dark. */
export const heldIn = (room: Room): Device | undefined => room.devices.find(d => !!heldOf(d))

/* ---------- previews: a screen held still without a controller in the room ---------- */

/* The brain's own words for each reason, as brain/hub/controller.py says them for the mock house's
   Under-cabinet strip -- copied, not paraphrased, so a preview shows exactly what a real one would. */
export const HELD_PREVIEW: Record<string, Held> = {
  supply: {
    held: 'supply', state: 'Staying off', tile: 'on a different power supply',
    text: 'It was set up on a 12 V power supply, and it’s on a 24 V one now. A 12 V strip would burn on 24 V, so the controller is keeping it off.',
    next: 'Plug the 12 V supply back in', after: 'It comes on by itself as soon as it has the right one.',
    row: 'Under-cabinet strip is staying off. It was set up on a 12 V power supply and it’s on a 24 V one now, so the controller is keeping it off to protect it. Plug the 12 V supply back in and it comes on by itself.',
    set_up_on: '12 V', now_on: '24 V', chip: 'The strip is staying off to protect itself',
  },
  range: {
    held: 'range', state: 'Staying off', tile: 'wrong kind of power supply',
    text: 'Its power supply gives 19 V. Strips are made for 5, 12 or 24 V, and 19 is none of them — it may be a laptop charger. Both strips on this controller are off.',
    next: 'Use the power supply that came with the strip', after: 'It comes on by itself once it has one.',
    row: 'Under-cabinet strip is staying off. Its power supply gives 19 V. Strips are made for 5, 12 or 24 V, and 19 is none of them — it may be a laptop charger. Both strips on this controller are off. Use the power supply that came with the strip.',
    set_up_on: '12 V', now_on: '19 V', chip: 'The strip is staying off to protect itself',
  },
  trips: {
    held: 'trips', state: 'Switched off', tile: 'it kept cutting out',
    text: 'It cut out five times in a minute, so the controller stopped trying. Something is drawing more than it should — a pinched or wet cable, or a fault in the strip.',
    next: 'Check the cable, then unplug the controller and plug it back in', after: '',
    row: 'Under-cabinet strip has switched off. It cut out five times in a minute, so the controller stopped trying. Something is drawing more than it should — a pinched or wet cable, or a fault in the strip. Check the cable, then unplug the controller and plug it back in.',
    chip: 'The strip switched itself off to protect itself',
  },
  wiring: {
    held: 'wiring', state: 'Switched off', tile: 'a wire in the wrong place',
    text: 'Power was reaching the wire that carries the colors — usually two wires swapped where the strip joins its cable. It was caught in time, and nothing is damaged.',
    next: 'Swap them back, then unplug the controller and plug it back in', after: '',
    row: 'Under-cabinet strip has switched off. Power was reaching the wire that carries the colors — usually two wires swapped where the strip joins its cable. It was caught in time, and nothing is damaged. Swap them back, then unplug the controller and plug it back in.',
    chip: 'The strip switched itself off to protect itself',
  },
  hot: { quiet: 'A little dimmer than that for now. The controller is warm, and it eases off until it cools. More air around it helps.' },
  full: { quiet: 'At full white this much strip asks a little more than the controller can give, so it holds just under. Nothing needs doing.' },
}

/** Put a preview report on the house's strip, as the brain would. The strip is the mock house's
 *  Under-cabinet strip (k2); a held one is dark, which is what the controller is doing. */
export function previewHeld(rooms: Room[], reason: string, id = 'k2'): void {
  const h = HELD_PREVIEW[reason]
  if (!h) return
  for (const r of rooms) for (const d of r.devices) {
    if (d.id !== id) continue
    d.attrs = { ...d.attrs, strip: h }
    if (h.held) d.state = 'off'
    else d.state = 'on'
  }
}

/** The Needs a look row the brain hands over for a held strip, for a preview. */
export const previewHeldNote = (reason: string, room = 'Kitchen', id = 'k2') => {
  const h = HELD_PREVIEW[reason]
  if (!h?.held) return null
  return { kind: 'held' as const, subject: id, since: null, where: `${room} · a light strip`, name: 'Under-cabinet strip',
           text: h.row!, band: `The ${room.toLowerCase()} strip ${h.state === 'Staying off' ? 'is staying off' : 'has switched off'}`,
           acts: [{ do: 'Show me', act: 'open' as const, to: id }] }
}

/* ---------- the roofline ---------- */

/* Emitter colors by name, the boards' own (design/roofline/OwnsA.dc.html `LED`). The panel draws them
   as what the roof is ASKED for, never as its own palette. */
export const LED: Record<string, [number, number, number]> = {
  red: [255, 45, 36], green: [20, 216, 96], orange: [255, 116, 16], purple: [154, 69, 255], white: [255, 241, 220],
  blue: [42, 99, 255], warm: [255, 199, 117], pink: [255, 127, 192], mint: [95, 240, 184], lilac: [169, 140, 255], gold: [255, 178, 30],
}

/** "1st", "2nd", "3rd": the order a run was tapped in, the way the yard board writes it. */
export function nth(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${s}`
}

/** What a yard row says under its color: whether it is next, done, or turned round (TapA.dc.html). */
export function yardSub(y: Yard, i: number): string {
  const r = y.rows[i]
  if (r.nth == null) {
    const tapped = y.rows.filter(x => x.nth != null).length
    return tapped === 0 || !y.rows.slice(0, i).some(x => x.nth == null) ? 'Tap it if it comes next' : 'Not yet'
  }
  return r.turned ? 'Turned round — its white light ran toward you' : 'Its white light runs your way'
}

/** The tile's state for the roofline: one light, on or off as one, with the occasion -- or which part is
 *  dark, because a dark garage end is not a dark house (OneLight.dc.html). */
export function roofTile(d: Device, r: Roofline | null): string {
  if (!r || !r.exists) return ''
  const dark = r.boxes.find(b => b.state !== 'Fine')
  if (d.state !== 'on') return 'Off'
  if (dark) return `On · the ${dark.place.replace(/^The /, '').toLowerCase()} is dark`
  return r.occasion_name ? `On · ${r.occasion_name}` : 'On'
}

/** "Three boxes, four runs", as the pane's head says it. */
export function roofCount(r: Extract<Roofline, { exists: true }>): string {
  const w = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']
  const n = (k: number, one: string, many: string) => `${w[k] ?? k} ${k === 1 ? one : many}`
  const s = `${n(r.boxes.length, 'controller', 'controllers')}, ${n(r.runs, 'strip', 'strips')}`
  return s[0].toUpperCase() + s.slice(1)
}

/** How much roof there is, in lights: a roofline's pitch is nobody's guess, so it is not turned into meters. */
export const roofMeters = (lights: number) => `${lights} lights`

/* The roofline the boards draw -- three boxes, four runs, at Christmas, with evenings -- for a preview.
   `kind` picks the moment: christmas | dark | ask | yard | done | halloween | still | none. */
export function previewRoofline(kind: string): Roofline {
  const dark = kind === 'dark'
  const occ = kind === 'halloween' ? ['halloween', 'Halloween', 'Orange and purple, unsteady like embers', 'flicker']
    : kind === 'none' ? [null, null, null, 'off'] : ['christmas', 'Christmas', 'Red and green, chasing each other slowly', 'chase']
  const yard: Yard | null = kind === 'yard' || kind === 'done' ? {
    step: kind === 'done' ? 'done' : 'tapping', all: kind === 'done',
    rows: [
      { chip: 'a', run: 1, name: 'Red', led: LED.red, place: 'Left corner', nth: 0, turned: false },
      { chip: 'b', run: 1, name: 'Blue', led: LED.blue, place: 'Right of the door', nth: 1, turned: true },
      { chip: 'b', run: 2, name: 'Green', led: LED.green, place: 'Right of the door', nth: kind === 'done' ? 2 : null, turned: false },
      { chip: 'c', run: 1, name: 'Pink', led: LED.pink, place: 'Garage end', nth: kind === 'done' ? 3 : null, turned: kind === 'done' },
    ],
  } : null
  /* The look as the brain gives it (roofline.py `look_of`): emitter colors, motion, block and pace. */
  const look = occ[0] === 'halloween' ? { colors: [LED.orange, LED.orange, LED.purple], block: 1, ms: 1600 }
    : occ[0] ? { colors: [LED.red, LED.green], block: 4, ms: 2800 } : { colors: [LED.warm], block: 1, ms: 0 }
  /* The way round as the board draws it: two runs turned against it, each run its own length. */
  const order = [{ chip: 'a', run: 1, dir: 1 }, { chip: 'b', run: 1, dir: -1 }, { chip: 'b', run: 2, dir: 1 }, { chip: 'c', run: 1, dir: -1 }]
  return {
    exists: true, light: 'roofline', runs: 4, lights: 412, order: kind === 'ask' || yard ? null : order, turned: 2,
    parts: [{ chip: 'a', run: 1, count: 110 }, { chip: 'b', run: 1, count: 110 }, { chip: 'b', run: 2, count: 96 }, { chip: 'c', run: 1, count: 96 }],
    ask_order: kind === 'ask', yard,
    boxes: [
      { chip: 'a', place: 'Left corner', runs: 1, online: true, state: 'Fine', sub: '' },
      { chip: 'b', place: 'Right of the door', runs: 2, online: true, state: 'Fine', sub: '' },
      dark ? { chip: 'c', place: 'Garage end', runs: 1, online: true, state: 'Dark', held: 'supply', dark_runs: [1], sub: 'On a different power supply. Plug the 12 V supply back in.' }
           : { chip: 'c', place: 'Garage end', runs: 1, online: true, state: 'Fine', sub: '' },
    ],
    evenings: 'every', evenings_words: 'Every evening', until: '23:00', until_words: '11 PM', dusk: null,
    still: kind === 'still', occasion: occ[0], occasion_name: occ[1],
    words: kind === 'still' ? 'Red and green, held still' : occ[2],
    look: kind === 'still' ? { motion: 'still', ...look, block: 4 } : { motion: occ[3] as string, ...look }, kept: [], draft: null,
    why: occ[1] ? `On at dusk because it keeps evenings. ${occ[1]} is on in the house, so that is how it looks.`
      : 'On at dusk because it keeps evenings, in its everyday warm white. No occasion, no colors.',
    came_on: null,
  }
}

/** The light the preview roofline is: one tile, in the yard. */
export const previewRoofDevice = (): Device => ({
  id: 'roofline', name: 'Roofline', room_id: 'backyard', capability: 'light', state: 'on',
  attrs: { brightness: 255, supported_color_modes: ['rgb'], color_mode: 'rgb', rgb_color: [255, 120, 90] }, hw: 'hw-roof-a',
})

/** The strip setup's new beats, for ?strip=: the second strip, its colors, a try the other way, and
 *  the two last beats for a light that is outside. */
export function previewStripBeat(beat: string, base: Strip): Strip | null {
  switch (beat) {
    case 'second': return { ...base, state: 'second' }
    case 'second-red': return { ...base, state: 'order', asking: 'red', run: 2, second: 'part' }
    case 'second-room': return { ...base, state: 'room', run: 2, second: 'own', placing_run: 2 }
    case 'lit': return { ...base, state: 'order', asking: 'lit' }
    case 'roofline': return { ...base, state: 'roofline', boxes: 2 }
    case 'evenings': return { ...base, state: 'evenings' }
    default: return null
  }
}

/* ---------- the band's lines from a controller and the roofline ----------
   Two arrivals, said the way a knock is: one line each, never a screen. A strip plugged into a second
   socket months later (AskWhichC: "Something new is plugged into the kitchen controller"), whose tap
   asks the same question setup would have; and the roofline coming on at dusk by itself, for an hour,
   whose tap is the undo (design/roofline/, "what all three keep"). */
export type ControllerLine = { id: string; title: string; sub: string; strip?: string; roof?: string }
export function controllerBand(strip: Strip | null, roof: Roofline | null, now = Date.now()): ControllerLine[] {
  const out: ControllerLine[] = []
  for (const p of strip?.plugged ?? [])
    out.push({ id: `plugged:${p.id}`, title: p.text, sub: 'Tap to say whether it is part of a light or a light of its own.', strip: p.id })
  if (roof?.exists && roof.came_on && now - roof.came_on.at * 1000 < 3600_000 && roof.light)
    out.push({ id: 'roof:on', title: roof.came_on.text, sub: `${roof.why} Tap to turn it off for tonight.`, roof: roof.light })
  return out
}

/** ?strip2=part|own: a controller with a second strip, for the strip row and what is behind it
 *  (design/controller-panel/ChangeLaterC.dc.html). The mock house's strip is given 1.2 m more. */
export function previewStripRow(row: StripRow | null, kind: string | null): StripRow | null {
  if (!row || (kind !== 'part' && kind !== 'own')) return row
  return { ...row, run2: { count: 72, order: row.order, own: kind === 'own' }, light: 'k2', light2: kind === 'own' ? 'k2-toe' : null }
}

