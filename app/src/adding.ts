// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Adding something to the house: the four beats, and the words they are allowed to use.
 *
 * ONE WAY IN. What have you got -> which one is yours -> letting it in -> it's in, which room.
 * Every route wears all four, in that order, with the same words on the buttons. Only beat two
 * changes shape, and it changes because the OBJECT differs -- some things blink, some have a button
 * to press, some have a code printed on them, some want signing in to. A person can see which of
 * those they are holding. Nobody can see which radio a thing uses, which is why the doors are things
 * and not wires. design/adding/Spine.dc.html and design/adding/Words.dc.html.
 *
 * The radios did not go anywhere: Zigbee, Z-Wave and Matter are still exactly what they were, and
 * the hub still picks between them. They stopped being the question on the way in.
 */
import { reloadHome, store } from './store'

/** The doors of beat one. Four is the whole catalogue; a fifth means the taxonomy is wrong. */
export type DoorId = 'wall' | 'thing' | 'brand' | 'house'
/** Beat two, by what the object can do about proving it is the one in your hand. */
export type Proof = 'blink' | 'press' | 'code' | 'signin' | 'house'

export type Door = { id: DoorId; icon: string; title: string; sub: string; proof: Proof }

const DOORS: Door[] = [
  { id: 'wall', icon: 'switch', title: 'A switch on the wall', sub: 'A switch or dimmer, new or already up', proof: 'blink' },
  { id: 'thing', icon: 'plug', title: 'A plug, bulb or sensor', sub: 'Something out of a box, in your hand', proof: 'press' },
  { id: 'brand', icon: 'plus', title: 'Something with its own app', sub: 'Hue, Sonos, Ring, a thermostat…', proof: 'signin' },
  { id: 'house', icon: 'home', title: 'A part of the house', sub: 'Another panel, or a bridge for your switches', proof: 'house' },
]

/** Which radios of the hub's own are up. The panel asks this to know what it can honestly offer. */
export const radiosUp = () => new Set((store.status?.drivers ?? []).filter(p => p.state === 'ready').map(p => p.id))
/** The ones a thing joins by being pressed. Matter is not one of them: it joins by its printed code. */
export const pressRadios = () => ['zigbee', 'zwave'].filter(r => radiosUp().has(r))
export const matterUp = () => radiosUp().has('matter')
/** A bridge is set up, so the switches already in the walls can be reached at all. */
export const bridged = () => (store.bridge?.bridges ?? 0) > 0

/* A door the house cannot walk through is not offered. 'Something with its own app' has no such test:
   the catalogue is always there, and searching it needs nothing of the hub. */
export function doors(): Door[] {
  return DOORS.filter(d =>
    d.id === 'wall' ? bridged()
    : d.id === 'thing' ? pressRadios().length > 0 || matterUp()
    : true)
}

/*
 * What a beat-two piece hands back when somebody has proved which object is theirs and the house has
 * let it in. `device_id` is what beat four needs to put it in a room; an account that brought in six
 * things at once has none, and says so with `many`.
 */
export type Caught = {
  device_id?: string
  name?: string          // what the house is calling it, which beat four offers to change
  what?: string          // what it turned out to be, in objects: "a light that dims, and a motion sensor"
  many?: boolean         // one account, several things: the room is asked under New devices instead
}

/** What beat three says while it works. `how_long` is honest or absent; never a guess dressed as one. */
export type Working = { text: string; how_long?: string }

/*
 * What a piece wants on the button row. The piece knows WHAT it needs offering ("I can reach the
 * code", "Try the next one"); the shell decides where those sit, what they look like, and that
 * "Not now" comes last. One place says the words, which is the whole point of the exercise.
 */
export type Act = { label: string; primary?: boolean; run: () => void }

/*
 * WHAT ARRIVED, for the routes that cannot say.
 *
 * A switch let in through the bridge hands back the device it became. A thing that joined a radio
 * does not: it lands in Home Assistant, and turns up in the house a second or two later with no room.
 * Without this, beat four for those routes would be the old paragraph -- "find it under New devices"
 * -- which is the house asking a person to go and finish its job.
 *
 * So the screen takes the house's devices before it opens the door, and looks for what is new after.
 * One newcomer can be placed and named on the spot. Several came from one account and go to New
 * devices, which is the screen for exactly that. Nothing new yet, after a fair wait, is also an
 * answer: it joined, and it will turn up.
 */
export const everyDevice = () => new Set(store.rooms.flatMap(r => r.devices.map(d => d.id)))

export async function whatArrived(before: Set<string>, tries = 6): Promise<Caught> {
  for (let i = 0; i < tries; i++) {
    await new Promise(r => setTimeout(r, 2000))
    await reloadHome()
    const now = store.rooms.flatMap(r => r.devices).filter(d => !before.has(d.id))
    if (now.length === 1) return { device_id: now[0].id, name: now[0].name, what: kindOf(now[0].capability) }
    if (now.length > 1) return { many: true, what: `${now.length} new things` }
  }
  return { many: true }
}

/* What a thing is, in the words a person would use for it. Never a protocol, never a count of
   entities -- and when the house genuinely does not know, it says so rather than guessing. */
const KINDS: Record<string, string> = {
  light: 'a light', dimmer: 'a light that dims', switch: 'a switch', plug: 'a plug that switches',
  lock: 'a lock', cover: 'a blind', climate: 'a thermostat', sensor: 'a sensor', motion: 'a motion sensor',
  contact: 'a door sensor', camera: 'a camera', media: 'a speaker', fan: 'a fan', appliance: 'an appliance',
}
export const kindOf = (capability?: string) => KINDS[capability ?? ''] ?? 'something new'

/*
 * The house's own sentence, turned back into a fragment.
 *
 * Beat four says "It turned out to be ___", and the bridge hands back a whole sentence for that
 * blank -- "A light that dims, and a motion sensor." Dropped in as it stands that reads with a
 * capital in the middle and two full stops at the end. So the full stop comes off, and the first
 * word is lowered only when it is one that has no business being capital.
 */
const OPENERS = new Set(['a', 'an', 'the', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'something', 'it'])
export function asThing(text?: string): string | undefined {
  const t = (text ?? '').trim().replace(/\.$/, '')
  if (!t) return undefined
  const [first] = t.split(/\s/)
  return OPENERS.has(first.toLowerCase()) ? first.toLowerCase() + t.slice(first.length) : t
}

/*
 * IS A LIGHT STRIP STILL ASKING?
 *
 * A strip's own sheet covers the whole screen the moment one knocks, so the only time this page is
 * visible with a strip waiting is when something has outranked it -- a bridge, because somebody is
 * holding the bridge (App.vue). The row it drives says where the strip is in the queue rather than
 * offering a button, because nothing tappable could bring the sheet forward while the bridge has it.
 *
 * Only the beats where it is still ASKING. A strip that is being set up, or is set up, or has
 * failed, is not something waiting to be let in, and listing it as one would be a second place in
 * the panel claiming to know the same thing -- which is how two screens start disagreeing.
 */
const STILL_ASKING = ['knocking', 'rhythm']
export const stripWaiting = (state?: string) => STILL_ASKING.includes(state ?? '')
