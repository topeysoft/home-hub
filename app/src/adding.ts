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
 * Only the beats where it is still ASKING. A strip that is being set up, or is set up, or has
 * failed, is not something waiting to be let in, and listing it as one would be a second place in
 * the panel claiming to know the same thing -- which is how two screens start disagreeing.
 *
 * THIS ROW USED TO HAVE NO BUTTON ON IT, and the comment here used to explain why: a strip's sheet
 * covered the whole screen the moment one knocked, so the only way to be looking at this page with
 * a strip waiting was for a bridge to have outranked it, and nothing tappable could have brought
 * the sheet forward. The sheet does not open itself any more (design/knock/), so the row is now the
 * ordinary way in and carries the ordinary button.
 */
const STILL_ASKING = ['knocking', 'press', 'rhythm']
export const stripWaiting = (state?: string) => STILL_ASKING.includes(state ?? '')

/*
 * WHEN AN ARRIVAL MAY TAKE A SCREEN, AND WHAT IT SAYS WHEN IT MAY NOT.
 *
 * design/knock/, direction C with A, chosen 22 September. A knock is one line in the band and a dot
 * on the + door -- which is exactly what the panel already did for a thing noticed on the network,
 * and never did for a knock. It fills a screen only where somebody was already asking.
 *
 * Both of the rules below are here rather than in a component because they are the decision, and a
 * decision drawn on a board should be readable in one place and pinned by a test that fails if it
 * drifts. app/tests/adding.test.ts.
 */

/** An hour. After this the knock's own line folds in with anything else waiting. */
export const SHOUTS_FOR = 60 * 60 * 1000

/**
 * May the strip's sheet be on screen?
 *
 * `asked` is somebody having tapped the line in the band or the row on Add. Standing on Add IS the
 * asking, so no tap is needed there -- that is the whole of direction C. Everything else in the
 * house is direction A: nothing takes the screen, ever.
 *
 * `putDown` is closing it, and it has to be remembered or Add cannot be stood on: without it the
 * page that opens the conversation opens it again the instant it is closed, and there is no way
 * back to the list of what else is waiting. Tapping the row asks again and wins.
 */
export const stripSheetOpen = (state?: string, sheet?: string | null, asked = false, putDown = false) =>
  !!state && state !== 'none' && (asked || (sheet === 'add' && !putDown) || !stripWaiting(state))

/**
 * What the band says about things waiting to be set up.
 *
 * A knock shouts for an hour -- its own line, its own sentence -- and then folds in with whatever
 * else is waiting, because a line that will not go away is the interruption again, slower. It stops
 * entirely when the thing stops knocking. The dot on the + door is not decided here and does not
 * fold: the house goes quiet, it does not forget.
 *
 * IT RETURNS A LIST BECAUSE A FRESH KNOCK IS AN EXTRA LINE AND NOT A REPLACEMENT. The first
 * version returned one, and a house with a Hue bridge on the network lost the line about it the
 * moment a strip was plugged in -- found by opening the panel and looking at the band, which is the
 * only instrument that would ever have shown it.
 *
 * `found` is the things noticed on the network, which have always been a line of this kind.
 */
export type BandLine = {
  id: 'knock' | 'waiting'
  title: string
  sub: string
  /** 'strip' is the conversation itself; 'waiting' opens Add and lets the rows there be the choice. */
  opens: 'strip' | 'add'
}

const foundLine = (found: { title: string }[]): BandLine => found.length === 1
  /* The words for one thing found nearby are the panel's own and predate all of this, so a house
     with nothing knocking sees no change at all. */
  ? { id: 'waiting', opens: 'add', title: `Found ${found[0].title}`, sub: 'Tap to add it to the house.' }
  : { id: 'waiting', opens: 'add', title: `Found ${found.length} new things nearby`,
      sub: found.slice(0, 3).map(f => f.title).join(', ') + (found.length > 3 ? '…' : '') }

export function waitingBand(
  found: { title: string }[], strip: { state?: string; since?: number } | null,
  now = Date.now(),
): BandLine[] {
  const knocking = stripWaiting(strip?.state)
  /* A hub too old to say when it started knocking has never said it, so the line would fold the
     instant it appeared. An unknown age is a new one: shout, and let the next hub be exact. */
  const fresh = knocking && (strip?.since == null || now - strip.since * 1000 < SHOUTS_FOR)
  if (fresh) return [
    { id: 'knock', opens: 'strip', title: 'A light strip is here',
      sub: 'Tap to set it up. It is lit, so you can see which one.' },
    ...(found.length ? [foundLine(found)] : []),
  ]
  if (!knocking) return found.length ? [foundLine(found)] : []
  /* Folded: the knock has stopped being about itself and is one of the things waiting. */
  const n = found.length + 1
  const names = [...found.slice(0, 3).map(f => f.title), 'a light strip']
  return [{
    id: 'waiting', opens: 'add',
    title: n === 1 ? '1 thing waiting to be set up' : `${n} things waiting to be set up`,
    sub: names.join(', ') + (found.length > 3 ? '…' : ''),
  }]
}
