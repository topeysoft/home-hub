// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The house, ranked: what order the Rooms tab puts the rooms in, and how much
 * of the screen each one gets. Drawn first as design/rooms/Main.dc.html.
 *
 * The tab used to be repeat(auto-fill, minmax(200px, 1fr)) -- every room the
 * same 218x108 box whether it was the room with the television on or the empty
 * bathroom. Measured at 1440x900 the grid came to 1360x226 in a 618px stage, so
 * two thirds of the screen was sky and the busiest room in the house had its
 * line ellipsised at "2 lights on · The Bear · Blind op…".
 *
 * This is the room screen's own grammar one level up -- three heights and
 * nothing else, columns filling down then right -- so the panel has one idea
 * about ranking rather than two. See views/RoomsView.vue for the grid, and
 * RoomCard.vue for what each size is allowed to say.
 */
import type { Device, Room } from './api'
import { activityParts, cap, isActive, isDead, roomActive } from './store'

export type Size = 'full' | 'half' | 'third' | 'row'
export type Cell = { id: string; size: Size }

const lit = (d: Device) => cap(d) === 'light' && d.state === 'on' && !isDead(d)
/** the media a room's lead card gives a row of its own to */
export const playingIn = (r: Room) => r.devices.find(d => cap(d) === 'media' && d.state === 'playing')
/** the light doing most of the lighting, and so the one worth a dimmer on a card */
export const leadLight = (r: Room) =>
  [...r.devices.filter(lit)].sort((a, b) => brightOf(b) - brightOf(a))[0]
const brightOf = (d: Device) => Number(d.attrs.brightness ?? 255)
/** a camera that is recording is doing something; one merely watching the porch is not */
const filming = (r: Room) => r.devices.some(d => cap(d) === 'camera' && d.state === 'recording')
/** the room's own temperature, when something in it reads one */
export function temperature(r: Room): string {
  const d = r.devices.find(d => d.capability === 'sensor.temperature' && Number.isFinite(Number(d.state)))
  return d ? `${Math.round(Number(d.state))}°` : ''
}

/* How much of the house's light this room is responsible for. Not a count of
   lamps: a kitchen at 100% is doing more to the house than an office at 70%,
   and the count cannot tell them apart. */
const litness = (r: Room) => r.devices.filter(lit).reduce((n, d) => n + brightOf(d), 0)
const doing = (r: Room) => r.devices.filter(d => isActive(d) && !isDead(d)).length

/*
 * Four tiers, and they are about what a person is looking for. Rooms that are
 * doing something, then rooms that are merely there, then rooms with nothing in
 * them, then the tray of things waiting to be put somewhere.
 *
 * New devices goes LAST on purpose, even though it is the only card on the
 * screen with something to ask. Ranked by urgency it would lead the house,
 * which makes the Rooms tab a to-do list; at the end it reads as an invitation
 * you pass on the way out, which is what it is.
 */
function tier(r: Room): number {
  if (r.id === 'unassigned') return 3
  if (!r.devices.length) return 2
  return roomActive(r) || filming(r) ? 0 : 1
}

/** The order the rooms are read in: down a column, then the next column right. */
export function rankRooms(rooms: Room[]): Room[] {
  return rooms
    .map((r, i) => ({ r, i }))
    .sort((a, b) =>
      tier(a.r) - tier(b.r) ||
      Number(!!playingIn(b.r)) - Number(!!playingIn(a.r)) ||
      litness(b.r) - litness(a.r) ||
      doing(b.r) - doing(a.r) ||
      a.i - b.i)
    .map(x => x.r)
}

/* How much the room has to say, counted rather than guessed: the same parts the
   card's own line is built from. */
const saying = (r: Room) => activityParts(r).length

/*
 * A row spans three of the grid's fifteen tracks, so five rows are exactly one
 * column -- which is where the 106px in design/rooms/QuietIndex.dc.html came
 * from, and it is also the rule: the index is WHOLE COLUMNS or it is nothing.
 *
 * Tried first as a simple threshold, and the mock house showed why it does not
 * work: four quiet rooms made one column with three rows in it and 240px of sky
 * underneath, which does not read as an index, it reads as a bug. So the
 * remainder -- the highest-ranked of the quiet rooms, the ones nearest to doing
 * something -- stay cards and join the bento above, and only whole columns of
 * five go to the index.
 *
 * The cost is honest and worth writing down: a house whose quiet end hovers
 * near a multiple of five will see the tab change shape as rooms come on and
 * go off. Nothing here is worth a hole in the wall to avoid that.
 */
/* What each size is worth in the grid's fifteen tracks. The same table the test
   adds up to check the wall comes out flush. */
const TRACKS = { full: 15, half: 10, third: 5, row: 3 } as const
const COLUMN = 15

const PER_COLUMN = 5

/*
 * ONE room leads, one stands beside it, and the quiet end of the house is an
 * index rather than a wall of empty cards.
 *
 * The room screen says it about lamps -- "a room with four lights on is not a
 * room with four headlines in it" -- and a house with four rooms on is not a
 * house with four headlines in it either. Sized by how busy each room is, an
 * evening with the kitchen, the office and the bedroom all on came out as three
 * big cards and no lead, which is the flat grid again with bigger boxes.
 *
 * What changed on 17 Sep 2026 is the other end. A room with nothing on has one
 * short sentence to its name, and a 300x186 card is three times the furniture
 * that sentence needs; ten of them ran the house off the right edge of a wall
 * panel and hid three rooms behind it. As rows they are an index you scan, the
 * house fits on one screen, and the space comes back to the rooms that are
 * actually doing something -- which is why the lead may now be FULL without a
 * screen on, so long as it has more than one thing to say. See
 * design/rooms/QuietIndex.dc.html.
 */
export function sizeRooms(ranked: Room[]): Cell[] {
  const quiet = ranked.filter(r => tier(r) > 0).length
  /* Is there an index at all. Fewer than a column of quiet rooms and the house
     is all cards, exactly as design/rooms/Main.dc.html drew it. */
  const index = quiet >= PER_COLUMN
  const cards = index ? flush(ranked, quiet) : ranked.length
  return ranked.map((r, i): Cell =>
    i >= cards ? { id: r.id, size: 'row' } : { id: r.id, size: sizeAt(r, i, cards < ranked.length) })
}

/* What a card is worth where it sits. The lead may take a whole column when
   there is an index behind it to make the room -- but only if it has more than
   one thing to say, because one lamp is one line and one line does not want a
   poster. */
function sizeAt(r: Room, i: number, index: boolean): Size {
  if (tier(r) > 0) return 'third'
  if (i > 1) return 'third'
  if (i === 1) return 'half'
  return playingIn(r) || (index && saying(r) >= 2) ? 'full' : 'half'
}

/*
 * HOW MANY ROOMS STAY CARDS, which is the rule the whole arrangement now turns on.
 *
 * It used to be the other way round: the index took quiet rooms in whole columns
 * of five and whatever would not fit stayed a card. That left the bento ending
 * wherever it happened to end, and tracks() closed the hole by giving the
 * remainder to the last card -- fine when the hole is at the foot of a column,
 * absurd when the last card STARTS one. On a thirteen-room house with one lamp
 * on, a room with "1 light off" to say was drawn a whole column tall.
 * design/rooms/Long.dc.html, and design/rooms/DemoteB.dc.html for this answer.
 *
 * So the BENTO is what ends flush, and the index takes the rest: the smallest
 * number of leading rooms whose cards come to whole columns, which is
 *
 *   at least two, because one room leading and one beside it is the
 *     arrangement, and a lead on its own is not;
 *   at least the number of rooms doing something, because those are never rows;
 *   at most one short of the house, because an index of nothing is not an index.
 *
 * One always exists once there is an index to have: every size is a multiple of
 * five, so three more cards carry the total through every multiple of fifteen,
 * and an index needs five quiet rooms before it exists at all.
 *
 * What it spends is the rule from 17 Sep 2026: the index is no longer whole
 * columns, so its last one can run short. That was chosen knowing it -- a short
 * column at the END of the house reads as the list finishing, where the same
 * hole in the middle of the index read as a bug.
 */
function flush(ranked: Room[], quiet: number): number {
  const least = Math.max(2, ranked.length - quiet)
  let sum = 0
  for (let i = 0; i < ranked.length; i++) {
    sum += TRACKS[sizeAt(ranked[i], i, true)]
    const k = i + 1
    if (k >= least && k < ranked.length && sum % COLUMN === 0) return k
  }
  return ranked.length          // nothing fits: the house is all cards, and has no hole to fill
}

export type Track = { span: number; at?: number }

/*
 * Where each cell sits in the grid, which the grid cannot be left to work out
 * on its own.
 *
 * A row is PLACED on its own track rather than flowed: flowed, a row that
 * happened to fit a leftover two tracks would take them and drag the rest of the
 * index up behind it. Five rows are one column, top to bottom, and the sixth
 * starts the next one over.
 *
 * There used to be a second job here -- the last card stretched to the foot of
 * its column, so `column dense` could not drop an index row into the hole the
 * cards left behind. sizeRooms() no longer leaves one: the bento ends on a
 * column boundary, or there is no index to backfill it with. See flush().
 */
export function tracks(plan: Cell[]): Track[] {
  const out: Track[] = plan.map(c => ({ span: TRACKS[c.size] }))
  const first = plan.findIndex(c => c.size === 'row')
  if (first >= 0) for (let i = first; i < plan.length; i++) out[i].at = 1 + 3 * ((i - first) % PER_COLUMN)
  return out
}

/** The whole arrangement, which is the two above and nothing else. */
export const arrangeRooms = (rooms: Room[]): Cell[] => sizeRooms(rankRooms(rooms))
