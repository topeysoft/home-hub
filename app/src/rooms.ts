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
import { cap, isActive, isDead, roomActive } from './store'

export type Size = 'full' | 'half' | 'third'
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

/*
 * ONE room leads, and one stands beside it. The rest are thirds.
 *
 * The room screen says it about lamps -- "a room with four lights on is not a
 * room with four headlines in it" -- and a house with four rooms on is not a
 * house with four headlines in it either. Sized by how busy each room is, an
 * evening with the kitchen, the office and the bedroom all on came out as three
 * big cards and no lead, which is the flat grid again with bigger boxes.
 *
 * The lead is FULL when something is playing in it, because that is the room
 * that cannot be said in one line: artwork, a title, a button and the lamps.
 * Without a screen on, the loudest room in the house still fits in a half.
 */
export function sizeRooms(ranked: Room[]): Cell[] {
  return ranked.map((r, i) => ({
    id: r.id,
    size: tier(r) > 0 || i > 1 ? 'third' : i === 0 ? (playingIn(r) ? 'full' : 'half') : 'half',
  }))
}

/** The whole arrangement, which is the two above and nothing else. */
export const arrangeRooms = (rooms: Room[]): Cell[] => sizeRooms(rankRooms(rooms))
