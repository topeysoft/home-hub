// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { reactive } from 'vue'
import { doRestart, type Rung, getBridge, type Bridge, getHome, getEvents, getAmbient, getScenes, getStatus, getDiscovered, getRoutines, getAssistant, getPresence, getHealth, getSounds, connect, act, setIntent, setHomeIntent, type Room, type Device, type Home, type Event, type Ambient, type Rules, type Status, type Found, type Intent, type Routine, type Assistant, type Presence, type Note, type Sound, requestUpdate, getPhones, type Phone, type Ask, getAccounts, type Account, getShare, type Share } from './api'
import { lock } from './code'
import { sunPosition, sunGuess, moonPhase } from './sun'

/* The few soft sheets the panel has. Named rather than written out twice: the restart keeps the one
   it closed so it can come back to it, and `typeof store.sheet` there would make the store's own type
   circular -- which typescript answers by quietly making the whole store `any`. */
export type Sheet = null | 'location' | 'add' | 'code' | 'why' | 'routines' | 'hub' | 'look' | 'house' | 'people' | 'accounts' | 'share' | 'notes'

export const store = reactive({
  rooms: [] as Room[], linkUp: false, linkLost: false, error: '', loaded: false,   // linkLost: down long enough to be worth mentioning
  toast: null as null | { id: number; text: string; kind: 'info' | 'error'; action?: { label: string; run: () => void } },   // a toast may carry one way back, like Undo
  pending: {} as Record<string, true>,     // devices waiting for the house to confirm a change
  viewer: null as Device | null,            // camera shown full screen
  events: [] as Event[],
  opened: null as Device | null,   // one device, held open in front of the house
  /* the weather, held open in the same pane. Its own flag rather than a seat in `opened`,
     because the weather is not a device and never will be: it has no id, no room and nothing
     to do to it, and widening `opened` to hold it would put a null check on every line that
     reads a device out of it. See WeatherPane.vue. */
  outside: new URLSearchParams(location.search).get('outside') === '1',   // ?outside=1 previews it, the way ?sheet= and ?rest=1 preview the others
  ambient: { location: null, weather: null } as Ambient,
  ambientLoaded: false,
  rules: {} as Rules,                        // scene rules from the brain, to tell whether a room still matches its scene
  sheet: (['location', 'add', 'code', 'why', 'routines', 'hub', 'look', 'house', 'people', 'accounts', 'share', 'notes'].includes(new URLSearchParams(location.search).get('sheet') ?? '') ? new URLSearchParams(location.search).get('sheet') : null) as Sheet,   // ?sheet=location previews one
  whyRoom: new URLSearchParams(location.search).get('room') as string | null,   // the room the why sheet is about; ?sheet=why&room=kitchen previews it
  resume: new URLSearchParams(location.search).get('signin') as string | null,   // a conversation already open in the house (signing an account in again); the add sheet picks it up. ?sheet=add&signin=<flow> previews it
  routines: [] as Routine[],                 // the brain's rules, for the routines sheet and to name a rule on a room
  routineErrors: [] as string[],             // rules the brain could not read, in its own words
  drafts: [] as Routine[],                   // routines the assistant wrote that wait for a person's OK
  entry: [] as string[],                     // the rooms people come in through; routines for "entry" run there
  assistant: null as Assistant | null,       // whether the hub can talk to the model at all
  presence: null as Presence | null,         // who is home, from the brain; null until it has said
  notes: [] as Note[],                       // what needs a look, in the brain's words
  accounts: [] as Account[],                 // the services the house has signed into, for the Accounts page and its door
  /* What this house gives out to other apps as Matter devices: its own page, and its own door, which
     says how things stand there without anybody opening it. Null until the hub has answered once. */
  share: null as Share | null,
  sounds: [] as Sound[],                     // what a speaker can play: the hub's noises and the files in its sounds folder
  /* An update is happening -- this screen asked, or the hub started one in the night and said so.
     For most of it the house is entirely usable: the code, the signature and the download all happen
     with the brain running, and the panel shows the phase as a line rather than throwing a blackout
     over a hub that is merely fetching something. `lost` is when the brain actually went, and only
     then does `left` count down, from the figure the HUB measured on its own last update. */
  updating: null as null | { at: number; dark: number; left: number; lost: boolean },
  restoring: false,                          // this screen sent a backup back; cleared when the hub returns
  /* This screen asked the hub to restart. `left` is the countdown the overlay draws, from the figure
     the HUB measured on its own last restart -- a spinner says "this may never end", a number that
     runs out says the house knows what it is doing. `lost` is the guard that makes coming back
     mean something: the link is still up for the second between the answer and the brain going, so
     nothing counts as back until it has first gone away. */
  restarting: null as null | { rung: Rung; at: number; seconds: number; left: number; lost: boolean; from: Sheet },
  previewSetup: new URLSearchParams(location.search).get('setup') === '1',   // ?setup=1 previews first run; cleared by Open Home
  status: null as Status | null,            // where the hub is in its life: engine down, fresh, ready; and whether setup finished
  phones: [] as Phone[], asks: [] as Ask[],  // the phones that belong to the house, and the ones asking to
  /* Sharing changed, or somebody scanned the code: a counter rather than the state itself, because
     only This hub draws it and a page that is not open should not be kept up to date. */
  shareTick: 0,
  /* a knock that has been put aside: the pane is down, the ask still stands, and the chip in the
     band carries it. A NEW knock clears this (App.vue), because putting one phone aside must not
     silence the next one. */
  askAside: false,
  homeName: '' as string,
  tempUnit: '' as string,                   // the house's temperature unit, from the home's location (°F in the US)
  found: [] as Found[],                      // things noticed on the network that are not set up yet
  /* Bridges: how many the house has, and the one job that may be running on one right now -- one at a
     time, because it is a person holding a thing. null on a hub that knows nothing about bridges at
     all, which is most of them. `state: 'none'` is a hub that has them and is not busy, which is not
     the same thing and is why this is not cleared to null -- see refreshBridge(). */
  bridge: null as Bridge | null,
  sky: { elevation: -20, azimuth: 0, phase: 0, hour: 0, month: 6, condition: 'clear-night', guessed: true },   // what the sky draws; month is seasonal (0 midwinter → 6 midsummer, either hemisphere)
})

/* ---------- the sky: sun from the clock and the location, weather from the house ---------- */
const params = new URLSearchParams(location.search)
const previewAt = params.get('at')          // ?at=18:30 previews an hour of the day
const previewWx = params.get('wx')          // ?wx=rainy previews a condition
const previewMonth = params.get('month')    // ?month=1 previews a season (1 January … 12 December, northern)
export const WEATHER_LABEL: Record<string, string> = {
  sunny: 'Clear', 'clear-night': 'Clear', partlycloudy: 'Partly cloudy', cloudy: 'Cloudy', fog: 'Fog', rainy: 'Rain', pouring: 'Heavy rain',
  hail: 'Hail', lightning: 'Storm', 'lightning-rainy': 'Thunderstorm', snowy: 'Snow', 'snowy-rainy': 'Sleet', windy: 'Windy', 'windy-variant': 'Windy', exceptional: 'Unusual weather',
}
export function updateSky() {
  const now = new Date()
  if (previewAt) { const [h, m] = previewAt.split(':').map(Number); now.setHours(h || 0, m || 0, 0, 0) }
  const loc = store.ambient.location
  const sun = loc ? sunPosition(now, loc.lat, loc.lon) : sunGuess(now)
  const condition = previewWx ?? store.ambient.weather?.condition ?? (sun.elevation < -6 ? 'clear-night' : 'sunny')
  const month = previewMonth ? Number(previewMonth) - .5 : (now.getMonth() + now.getDate() / 31 + (loc && loc.lat < 0 ? 6 : 0)) % 12   // south of the equator the seasons swap
  store.sky = { ...sun, phase: moonPhase(now), hour: now.getHours() + now.getMinutes() / 60, month, condition, guessed: !loc }
}
/* the two halves separately, for a layout that sets them at different sizes */
export function weatherParts(): { temp: string; label: string } {
  const w = store.ambient.weather
  if (!w && !previewWx) return { temp: '', label: '' }
  return {
    temp: w?.temperature != null ? `${Math.round(w.temperature)}${(w.unit || '°').replace(/[^°]/g, '') || '°'}` : '',
    label: WEATHER_LABEL[previewWx ?? w?.condition ?? ''] ?? '',
  }
}
export function weatherLine(): string {
  const { temp, label } = weatherParts()
  return [temp, label].filter(Boolean).join(' · ')
}
async function loadRules() { try { store.rules = await getScenes() } catch {} }
async function loadAmbient() {
  try { store.ambient = await getAmbient(); store.ambientLoaded = true } catch {}
  updateSky()
}

const ACTIVE = new Set(['on', 'playing', 'open', 'unlocked', 'cleaning', 'streaming', 'recording'])
export const isActive = (d: Device) => ACTIVE.has(d.state)
export const isDead = (d: Device) => d.state === 'unavailable' || d.state === 'unknown'
/* What the house treats a thing AS: the owner's answer where they have given one, the driver's otherwise.
   Every tile, pane, verb and room line reads this. Nothing that picks a service does -- that is the
   brain's job, from `capability`, and the panel never sees it. See docs/kinds.md. */
export const cap = (d: Device) => (d.kind || d.guess || d.capability).split('.')[0]
/** What it is shown as when nobody has said otherwise: the house's guess from its name where it made
    one (a switch on a fridge is an appliance), the driver's word where it did not. */
export const defaultKind = (d: Device) => d.guess || d.capability
/** Said quietly under the name on a thing's own pane, and nowhere else: a tile is a glance, and the
    point of the override is that the thing stops looking unusual. Empty where nobody has said anything. */
export const shownAs = (d: Device) => d.kind && d.kind !== defaultKind(d) ? `Shown as ${KIND_NOUN[cap(d)] ?? cap(d)}` : ''
export const KIND_NOUN: Record<string, string> = { light: 'a light', switch: 'a plug', fan: 'a fan', alarm: 'an alarm', appliance: 'an appliance', media: 'a speaker', cover: 'a blind', climate: 'a thermostat', lock: 'a lock', camera: 'a camera', vacuum: 'a vacuum' }
/** The glyph for a thing, which for an appliance reads its name: a fridge's ice maker gets the snowflake
    the weather already draws, and any other machine's feature the machine. Every other kind is its own icon. */
export const iconFor = (d: Device) => cap(d) === 'appliance' && /\bice\b|freez/i.test(d.name) ? 'snow' : cap(d)
export const PASSIVE = new Set(['sensor', 'motion', 'contact', 'camera'])
export const visibleRooms = () => {
  const rs = store.rooms.filter(r => r.id !== 'unassigned' || r.devices.length)
  return [...rs.filter(r => r.devices.length), ...rs.filter(r => !r.devices.length)]   // rooms with something in them first
}
export const roomOf = (d: Device) => store.rooms.find(r => r.id === d.room_id)
export const deviceById = (id: string) => { for (const r of store.rooms) { const d = r.devices.find(x => x.id === id); if (d) return d } }

/* ---------- names: say "Speaker" inside the Bedroom, not "Bedroom speaker" ---------- */
const GENERIC = /^((ceiling|floor|desk|table|main|left|right|wall|bedside|overhead|front|back|side) )?(speaker|tv|television|light|lights|lamp|fan|lock|door|blind|blinds|shade|shades|camera|plug|switch|thermostat|vacuum|window|motion|sensor|strip|doorbell|alarm|siren)$/i
const norm = (s: string) => s.replace(/[’‘]/g, "'").toLowerCase().trim()
/** A part named after its unit and its kind -- "Walkway Pathlight" + "Light", the way HA composes them -- IS the
    unit, on the wall: its tile wears the unit's name, and renaming it renames the unit (units.ts, docs/units.md). */
export function unitNamed(d: Device): boolean {
  const unit = (d.hw_name ?? '').trim()
  if (d.attrs.fan) return false   // the light of a fan-with-a-light is "Bedroom Fan Light", not the fan: under a lamp drawing, "Fan" reads as the wrong thing
  return !!unit && new RegExp(`^${unit.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+(light|switch|fan|plug|dimmer)$`, 'i').test(d.name.trim())
}
export function shortName(d: Device, room?: Room | null): string {
  let n = d.name.trim()
  if (unitNamed(d)) n = (d.hw_name ?? '').trim()
  if (room) {
    const r = norm(room.name), nn = norm(n)
    if (nn.startsWith(r + ' ')) {
      const rest = n.slice(r.length + 1).trim()
      if (rest && GENERIC.test(rest)) n = rest   // "Bedroom TV" → "TV"; "Garage View" (a camera's own name) stays whole
    }
  }
  return n.charAt(0).toUpperCase() + n.slice(1)
}

/* ---------- one line about a room, written for a person ---------- */
/*
 * The line before it is joined, because one card wants it short by one phrase.
 *
 * The Rooms tab's lead card spends a whole row on what is playing -- the
 * artwork, the title, the button -- so repeating "The Bear" in the line above
 * it says the same thing twice and pushes what ELSE the room is doing off the
 * end. `withMedia: false` leaves the row to say it. Every other caller joins
 * them all, which is what activity() below does.
 */
export function activityParts(r: Room, withMedia = true): string[] {
  const parts: string[] = []
  /* First, and on its own terms. Everything else in this line is what a room is doing;
     a siren is what a room is SHOUTING, and it does not queue behind the lamps. */
  if (r.devices.some(d => cap(d) === 'alarm' && d.state === 'on')) parts.push('Alarm sounding')
  const lights = r.devices.filter(d => cap(d) === 'light' && d.state === 'on').length
  if (lights) parts.push(lights === 1 ? '1 light on' : `${lights} lights on`)
  if (withMedia) for (const d of r.devices.filter(d => cap(d) === 'media' && d.state === 'playing'))
    parts.push(d.attrs.media_title ? `${d.attrs.media_title}` : `${shortName(d, r)} playing`)
  const open = r.devices.filter(d => cap(d) === 'cover' && d.state === 'open').length
  if (open) parts.push(open === 1 ? 'Blind open' : `${open} blinds open`)
  if (r.devices.some(d => cap(d) === 'lock' && d.state === 'unlocked')) parts.push('Unlocked')
  const plugs = r.devices.filter(d => cap(d) === 'switch' && d.state === 'on')
  if (plugs.length === 1) parts.push(`${shortName(plugs[0], r)} on`); else if (plugs.length) parts.push(`${plugs.length} plugs on`)
  for (const d of r.devices.filter(d => cap(d) === 'fan' && d.state === 'on')) parts.push(`${shortName(d, r)} on`)
  for (const d of r.devices.filter(d => cap(d) === 'vacuum' && d.state === 'cleaning')) parts.push(`${shortName(d, r)} cleaning`)
  if (r.devices.some(d => cap(d) === 'motion' && d.state === 'on')) parts.push('Motion')
  if (r.devices.some(d => cap(d) === 'camera' && d.state === 'recording')) parts.push('Recording')
  return parts
}
/*
 * What a room is HOLDING, for a card that would otherwise say "Quiet".
 *
 * On a house of thirteen rooms, ten cards said the same word, which is the
 * whole right-hand side of the Rooms tab saying nothing ten times over.
 * design/rooms/Main.dc.html never drew that word: its quiet rooms said "Door
 * closed · Camera idle", "Locked · Doorbell watching", "Mower docked". This is
 * that line, and it was in the spec before it was a complaint.
 *
 * The grammar is activityParts' own, one state along. What is being KEPT --
 * locked, shut, watched -- comes first, because that is what a person checks a
 * quiet room for; what is merely off comes after it. Two parts at most: a third
 * of a card is 260px wide and a third phrase is an ellipsis.
 */
export function restingParts(r: Room): string[] {
  const parts: string[] = []
  const locks = r.devices.filter(d => cap(d) === 'lock' && !isDead(d))
  if (locks.length && locks.every(d => d.state === 'locked')) parts.push('Locked')
  const shut = r.devices.filter(d => cap(d) === 'cover' && d.state === 'closed').length
  if (shut) parts.push(shut === 1 ? 'Blind closed' : `${shut} blinds closed`)
  /* A camera watching the porch is not the house doing something -- roomActive
     says so, and that is why the porch is a quiet room at all. It is still the
     truest thing a quiet porch has to say. */
  const eyes = r.devices.filter(d => cap(d) === 'camera' && !isDead(d)).length
  if (eyes) parts.push(eyes === 1 ? 'Camera watching' : `${eyes} cameras watching`)
  const screens = r.devices.filter(d => cap(d) === 'media' && !isDead(d))
  if (screens.length === 1) parts.push(`${shortName(screens[0], r)} off`)
  else if (screens.length) parts.push(`${screens.length} screens off`)
  const fans = r.devices.filter(d => cap(d) === 'fan' && !isDead(d))
  if (fans.length === 1) parts.push(`${shortName(fans[0], r)} off`)
  else if (fans.length) parts.push(`${fans.length} fans off`)
  const lamps = r.devices.filter(d => cap(d) === 'light' && !isDead(d)).length
  if (lamps) parts.push(lamps === 1 ? '1 light off' : `${lamps} lights off`)
  const plugs = r.devices.filter(d => cap(d) === 'switch' && !isDead(d)).length
  if (plugs) parts.push(plugs === 1 ? '1 plug off' : `${plugs} plugs off`)
  return parts.slice(0, 2)
}

/*
 * The line under a room's name, in two readings of the same sentence.
 *
 * `activity` is what the room is DOING, and it is what the three home layouts
 * have always shown -- it still ends at "Quiet", because RoomGrid's card is
 * one band among several and a band of resting states is a band of noise.
 * `restingLine` is the Rooms tab's, where the card is the whole subject and
 * "Quiet" is the absence of one. Only the two fallbacks differ, so the two
 * readings can never disagree about a room that is actually doing something.
 */
export function activity(r: Room): string { return roomLine(r, false) }
export function restingLine(r: Room): string { return roomLine(r, true) }
function roomLine(r: Room, resting: boolean): string {
  const parts = activityParts(r)
  if (parts.length) return parts.join(' · ')
  if (r.id === 'unassigned') return r.devices.length === 1 ? '1 to place' : `${r.devices.length} to place`
  if (!r.devices.length) return 'Nothing here yet'
  if (resting) {
    const rest = restingParts(r)
    if (rest.length) return rest.join(' · ')
  }
  if (r.devices.every(d => cap(d) === 'camera')) return r.devices.length === 1 ? '1 camera' : `${r.devices.length} cameras`
  return 'Quiet'
}
/* An appliance's feature being on is not the house doing anything: an ice maker is on all year, and a
   card for it in "on right now" would be a card that never leaves. It is on its own tile, and that is where. */
export function roomActive(r: Room) { return r.devices.some(d => isActive(d) && cap(d) !== 'camera' && cap(d) !== 'appliance') }
/** Everything that is on across the house, cameras and appliances excluded: the "on right now" strip. */
export function whatsOn(): Device[] {
  return store.rooms.flatMap(r => r.devices.filter(d => isActive(d) && !PASSIVE.has(cap(d)) && cap(d) !== 'appliance'))
}
export function houseLine(): string {
  if (!store.loaded) return store.error || 'Finding the house…'
  const on = whatsOn(), out = store.presence?.somebody === false
  const rooms = new Set(on.map(d => d.room_id))
  const what = !on.length ? '' : rooms.size === 1 ? `something is on in the ${roomOf(on[0])?.name ?? 'house'}` : `something is on in ${rooms.size} rooms`
  if (out) return what ? `Nobody's home, but ${what}.` : `Nobody's home${sinceText()}. ${store.homeName || 'The house'} is quiet.`
  if (!what) return `${store.homeName || 'The house'} is quiet.`
  return what.charAt(0).toUpperCase() + what.slice(1) + '.'
}
/** " since 5:10 pm", or " since yesterday", or nothing when the brain has no time for it. */
function sinceText(): string {
  const s = store.presence?.since; if (!s) return ''
  const d = new Date(s * 1000), today = new Date(); today.setHours(0, 0, 0, 0)
  if (d.getTime() >= today.getTime()) return ` since ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
  if (d.getTime() >= today.getTime() - 86400000) return ' since yesterday'
  return ` since ${d.toLocaleDateString([], { weekday: 'long' })}`
}

/* ---------- scenes: every button says what it will do ---------- */
export type Scene = { id: string; label: string; icon: string; needs: string[]; hint: (caps: Set<string>) => string }
const join = (xs: string[]) => xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]
const offList = (caps: Set<string>, extra = false) => join([
  caps.has('light') ? 'lights' : '', caps.has('media') ? 'screens' : '', extra && caps.has('switch') ? 'plugs' : '',
].filter(Boolean))
export const SCENES: Scene[] = [
  { id: 'movie', label: 'Movie', icon: 'film', needs: ['media'], hint: c => c.has('light') ? 'Lights low, screen on' : 'Screen on' },
  { id: 'guests', label: 'Guests', icon: 'sparkle', needs: ['light'], hint: () => 'Lights up bright' },
  { id: 'asleep', label: 'Sleep', icon: 'moon', needs: ['light', 'media', 'lock'], hint: c => `${cap1(offList(c))} off${c.has('lock') ? ', door locked' : ''}` },
  { id: 'empty', label: 'All off', icon: 'power', needs: ['light', 'media', 'switch', 'fan'], hint: c => cap1(join([c.has('light') ? 'lights off' : '', c.has('media') ? 'media paused' : ''].filter(Boolean))) },
]
export const HOUSE_SCENES: Scene[] = [
  { id: 'asleep', label: 'Bedtime', icon: 'moon', needs: [], hint: c => `${cap1(offList(c) || 'everything')} off in every room${c.has('lock') ? ', doors locked' : ''}` },
  { id: 'away', label: 'Everything off', icon: 'leave', needs: [], hint: c => `${cap1(offList(c, true) || 'everything')} off${c.has('lock') ? ', doors locked' : ''}` },
]
const cap1 = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
export const capsOf = (devices: Device[]) => new Set(devices.map(cap))
export function scenesFor(room: Room | null): Scene[] {
  if (!room) return store.rooms.some(r => r.devices.some(d => !PASSIVE.has(cap(d)))) ? HOUSE_SCENES : []
  const caps = capsOf(room.devices)
  return SCENES.filter(s => s.needs.some(c => caps.has(c)))
}
/* a scene 'holds' while every device it touches is still where the scene left it */
const EXPECT: Record<string, string[]> = { on: ['on', 'playing', 'paused', 'idle', 'buffering'], off: ['off', 'standby'], pause: ['paused', 'off', 'idle', 'standby'],
  play: ['playing'], lock: ['locked'], unlock: ['unlocked'], open: ['open', 'opening'], close: ['closed', 'closing'] }
export function sceneHolds(room: Room, id: string): boolean {
  const acts = store.rules[id]
  if (!acts || !acts.length) return false
  let touched = 0
  for (const [c, a] of acts) {
    const want = EXPECT[a]; if (!want) continue
    for (const d of room.devices) {
      if (cap(d) !== c || isDead(d)) continue
      touched++
      if (!want.includes(d.state)) return false
    }
  }
  return touched > 0
}
export function currentScene(room: Room): string | null {
  return room.intent && sceneHolds(room, room.intent) ? room.intent : null
}
export async function runScene(room: Room | null, scene: Scene): Promise<boolean> {
  try {
    if (room) { await setIntent(room.id, scene.id); room.intent = scene.id; notify(`${room.name} · ${scene.label}`) }
    else { await setHomeIntent(scene.id); for (const r of store.rooms) if (r.devices.length) r.intent = scene.id; notify(scene.id === 'asleep' ? 'Good night. The house is off.' : 'Everything is off.') }
    return true
  } catch (e: any) { notify(`That didn't work: ${e.message}`, 'error'); return false }
}

/* ---------- actions with instant feedback ---------- */
let toastId = 0, toastTimer: number | undefined
export function notify(text: string, kind: 'info' | 'error' = 'info', action?: { label: string; run: () => void }) {
  store.toast = { id: ++toastId, text, kind, action }
  clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => (store.toast = null), kind === 'error' ? 5000 : action ? 6000 : 2800)   // long enough to reach for Undo
}
export function dismissToast() { store.toast = null; clearTimeout(toastTimer) }

/* ---------- what you have just done, still on the screen ---------- */
/*
 * A thing you have just quieted is off, and Home's row is a row of what is on,
 * so the card it stood in had no reason to be there any more and left a beat
 * after the tap. That beat was the wrong answer to "did that work": the screen
 * took the thing away instead of telling you about it, and the row closing over
 * the gap moved everything else under the hand that was still there.
 *
 * So it stays. The card keeps its place, drained, saying what it now is and when
 * it became that, and tapping it again puts it back -- an undo in the place the
 * person is already looking, for as long as they are looking, rather than one
 * riding out on a toast. It is marked before the house is asked, like the state
 * the guess sets, because by the time the round trip is back the thing has
 * already left `whatsOn()` and the row would have closed over it unmarked.
 *
 * What clears it is the panel LOOKING AWAY: a wall going to rest, a phone going
 * behind another app, or -- for a screen nobody ever leaves -- half an hour.
 * Nobody is watching at that moment, so the row can close over the gap without
 * anything moving under a finger. App.vue owns those three moments; every part
 * of Home reads the same map, so a layout cannot disagree about it.
 *
 * A scene is not in here. "Everything off" means the row to empty, and that
 * emptying is the confirmation; ten gray cards would argue with it.
 */
export const done = reactive<Record<string, { verb: string; at: number }>>({})
const QUIETED: Record<string, string> = { off: 'Off', close: 'Closed', lock: 'Locked', pause: 'Paused' }
const WOKEN = new Set(['on', 'open', 'unlock', 'play'])
/* Held high on purpose: this is a stop on memory, not a policy about the screen. A cap a person can
   reach by turning off the lights in four rooms would take the earliest card back out from under them,
   which is the very thing this exists to stop; Home clips what it can draw at its own end. */
const DONE_KEEP = 24, DONE_FOR = 30 * 60 * 1000
function markDone(id: string, verb: string) {
  done[id] = { verb, at: Date.now() }
  const ids = Object.keys(done)
  if (ids.length > DONE_KEEP)
    for (const old of ids.sort((a, b) => done[a].at - done[b].at).slice(0, ids.length - DONE_KEEP)) delete done[old]
}
/** The panel looked away (all), or has simply been holding one too long (the rest). */
export function forgetDone(all = false) {
  const now = Date.now()
  for (const id of Object.keys(done)) if (all || now - done[id].at > DONE_FOR) delete done[id]
}
/** What Home is still showing though it is off: quieted by hand, not yet forgotten. */
export function justDone(): Device[] {
  return Object.keys(done).map(deviceById).filter((d): d is Device => !!d && !isActive(d) && !PASSIVE.has(cap(d)))
}
/** "Off, just now" -- what a kept card says about itself. */
export function doneLine(id: string, now = Date.now()): string {
  const d = done[id]; if (!d) return ''
  return `${d.verb} · ${ago(d.at / 1000, now).toLowerCase()}`
}
/* What the house is about to say, said now.
 *
 * A device object is the one the store holds -- a pane is handed it, not a copy -- so writing the
 * expected reading into it is how the drawing moves before the hub has answered. `perform` does it
 * either side of the request, and a pane under a finger does it with no request at all: while a
 * finger is down the drawing moves and the house is left alone, and only the release asks for
 * anything (panes/slide.ts). That second case used to be written out longhand in each pane, as an
 * assignment through `props.device` -- the same write as this, from a place a component is not
 * allowed to write from. The write was never the problem; the address was. So it lives here, where
 * the store's own object is the store's to change, and a pane asks for it by name. */
export function guessNow(d: Device, guess: { state?: string; attrs?: Record<string, any> }) {
  if (guess.state) d.state = guess.state
  if (guess.attrs) d.attrs = { ...d.attrs, ...guess.attrs }
}
/** Apply the expected result right away, ask the house, and step back if it refuses. */
export async function perform(d: Device, action: string, data?: Record<string, unknown>, guess?: { state?: string; attrs?: Record<string, any> }) {
  const before = { state: d.state, attrs: { ...d.attrs } }, wasDone = done[d.id]
  if (guess) guessNow(d, guess)
  /* guessed, with the state: what this did is the card's own sentence once it is no longer on */
  if (QUIETED[action]) markDone(d.id, QUIETED[action]); else if (WOKEN.has(action)) delete done[d.id]
  store.pending[d.id] = true
  try { await act(d.id, action, data) }
  catch (e: any) {
    d.state = before.state; d.attrs = before.attrs; delete store.pending[d.id]
    if (wasDone) done[d.id] = wasDone; else delete done[d.id]
    notify(`${shortName(d, roomOf(d))} didn't respond`, 'error'); return false
  }
  window.setTimeout(() => delete store.pending[d.id], 5000)   // the stream normally clears it much sooner
  return true
}

/* ---------- recent activity, told plainly ---------- */
export const LABELS: Record<string, string> = { movie: 'Movie', guests: 'Guests', asleep: 'Sleep', empty: 'All off', away: 'Everything off', occupied: 'In use' }
export function describe(ev: Event): { text: string; icon: string } | null {
  if (ev.kind === 'phone') {
    let d: any = {}; try { d = ev.detail ? JSON.parse(ev.detail) : {} } catch {}
    const n = d.name || 'A phone'
    return ev.new === 'joined' ? { text: `${n} joined the house`, icon: 'phone' } : ev.new === 'asked' ? { text: `${n} asked to join`, icon: 'phone' }
      : ev.new === 'removed' ? { text: `${n} was removed`, icon: 'phone' } : ev.new === 'left' ? { text: `${n}'s stay ended`, icon: 'phone' } : null
  }
  if (ev.kind === 'presence') return ev.new === 'nobody' ? { text: 'Everyone is out', icon: 'leave' } : ev.new === 'somebody' ? { text: 'Someone is home', icon: 'home' } : null
  if (ev.kind === 'intent') {
    if (ev.subject === 'home') return { text: ev.new === 'asleep' ? 'Bedtime' : LABELS[ev.new ?? ''] ?? ev.new ?? '', icon: ev.new === 'asleep' ? 'moon' : 'leave' }
    const r = store.rooms.find(r => r.id === ev.subject)
    return r ? { text: `${r.name} set to ${LABELS[ev.new ?? ''] ?? ev.new}`, icon: 'sparkle' } : null
  }
  if (ev.kind !== 'state' || ev.old === ev.new) return null
  const d = deviceById(ev.subject); if (!d) return null
  const n = d.name, k = cap(d), s = ev.new ?? ''
  if (s === 'unavailable') return { text: `${n} went offline`, icon: k }
  if (ev.old === 'unavailable') return { text: `${n} is back`, icon: k }
  let detail: any = null; try { detail = ev.detail ? JSON.parse(ev.detail) : null } catch {}
  if (k === 'light' || k === 'switch' || k === 'fan') return s === 'on' || s === 'off' ? { text: `${n} turned ${s}`, icon: k } : null
  if (k === 'media') {
    if (s === 'playing') return { text: detail?.media_title ? `${n} started playing ${detail.media_title}` : `${n} started playing`, icon: k }
    if (s === 'paused') return { text: `${n} paused`, icon: k }
    if (s === 'off') return { text: `${n} turned off`, icon: k }
    return null
  }
  if (k === 'camera') return s === 'recording' ? { text: `${n} started recording`, icon: k } : null
  if (k === 'motion') return s === 'on' ? { text: motionText(d), icon: k } : null
  if (k === 'contact') return s === 'on' ? { text: `${n} opened`, icon: k } : s === 'off' ? { text: `${n} closed`, icon: k } : null
  if (k === 'lock') return s === 'locked' || s === 'unlocked' ? { text: `${n} ${s}`, icon: k } : null
  if (k === 'cover') return s === 'open' || s === 'closed' ? { text: `${n} ${s === 'open' ? 'opened' : 'closed'}`, icon: k } : null
  return null
}
/** "Motion in the Kitchen" when the sensor is just called Motion; the sensor's own name when it has one. */
function motionText(d: Device): string {
  const r = roomOf(d)
  const rest = r && norm(d.name).startsWith(norm(r.name) + ' ') ? d.name.slice(r.name.length + 1) : d.name
  return r && /^((motion|sensor|detector)\s*)+$/i.test(rest.trim()) ? `Motion in the ${r.name}` : `Motion at ${d.name}`
}
export function ago(ts: number, now = Date.now()): string {
  const s = Math.max(0, (now - ts * 1000) / 1000)
  if (s < 60) return 'Just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts * 1000).toLocaleDateString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}
let eventsTimer: number | undefined
export async function refreshEvents() {
  try { store.events = await getEvents(60) } catch {}
}
function eventsSoon() { clearTimeout(eventsTimer); eventsTimer = window.setTimeout(refreshEvents, 1500) }

/* ---------- routines: what the house does on its own, and why a room is the way it is ---------- */
export async function loadRoutines() {
  try { const f = await getRoutines(); store.routines = f.rules ?? []; store.routineErrors = f.errors ?? []; store.drafts = f.drafts ?? [] } catch {}
}
export async function loadAssistant() {
  try { store.assistant = await getAssistant() } catch {}
}
export async function loadPresence() {
  try { store.presence = await getPresence() } catch {}
}
export async function loadSounds() {
  try { store.sounds = (await getSounds()).sounds } catch {}
}
export async function loadHealth() {
  if (store.status?.driver !== 'ready') return
  try { store.notes = (await getHealth()).notes } catch {}
}
export const routineById = (id: string) => store.routines.find(r => r.id === id)
/** An update the hub should raise by itself, and nothing is already installing it. `offer` rather
    than `available` so a version that was tried and rolled back is not pushed at anybody again; it
    is still installable from This hub, where a person is the one choosing. */
export function updateReady(): boolean { const u = store.status?.update; return !!u?.offer && u.state?.state !== 'running' && !u.requested && !store.updating }
/** Install the update that is waiting, from wherever it is offered: the nudge in the band and the
    Needs a look page both ask for the same one thing, and the host does the work. */
export async function installUpdate(): Promise<boolean> {
  try {
    const u = await requestUpdate()
    if (store.status) store.status.update = u
    beginUpdate(u.dark_seconds)
    notify('Installing. Everything keeps working while it downloads.')
    return true
  } catch (e: any) { notify(e.message, 'error'); return false }
}
/** Seconds as a household says them. The same rounding as the brain's `plainly`, because the two
    quote the same figures at people and disagreeing about them would be worse than either. */
export const plainly = (s: number) => s < 90 ? `about ${Math.round(s / 10) * 10} seconds` : `about ${Math.round(s / 60)} minutes`
let updateTick: number | undefined
/** An update is under way: this screen asked for it, or the hub started one in the night and the
    status said so on the way past. Either way the panel has to be able to draw the wait.

    The number counts the DARK stretch and nothing else, and it does not start running until the
    brain has actually gone. Before that the phase the hub is reporting is a better answer than any
    number, because it is true: for most of an update the house is entirely usable and the honest
    thing to show is a line saying what is being downloaded, not a screen saying come back later. */
export function beginUpdate(dark?: number) {
  const secs = dark || store.status?.update?.dark_seconds || 60
  if (store.updating) { store.updating.dark = secs; return }
  store.updating = { at: Date.now(), dark: secs, left: secs, lost: false }
  clearInterval(updateTick)
  updateTick = window.setInterval(() => { if (store.updating?.lost) store.updating.left = Math.max(0, store.updating.left - 1) }, 1000)
}
export function endUpdate() { store.updating = null; clearInterval(updateTick) }
/** The live stream going down while an update is in the air: from here on the hub cannot be asked
    anything, so the countdown takes over from the phase. Coming back is not handled here -- an
    update ends by the brain answering as a new build, which the status handler reads. */
export function updateLink(up: boolean) { if (store.updating && !up) store.updating.lost = true }
/* ---------- turning it off and on again ---------- */
let restartTick: number | undefined
/** Restart, at the rung the hub chose. The panel keeps its own stopwatch rather than asking the hub
    how long it was gone: the hub cannot answer that question while it is the thing that is away. */
export async function restartHub(rung: Rung = 'hub', understood = false): Promise<boolean> {
  try {
    const r = await doRestart(rung, understood)
    /* The sheet that asked closes, because the waiting screen IS the answer to the tap and a page
       about the hub is not a thing to read while the hub is leaving. Where it was is kept, and the
       panel comes back to it: the person was on This hub, so that is where they are when it returns. */
    store.restarting = { rung, at: Date.now(), seconds: r.seconds, left: r.seconds, lost: false, from: store.sheet }
    store.sheet = null
    clearInterval(restartTick)
    restartTick = window.setInterval(() => { if (store.restarting) store.restarting.left = Math.max(0, store.restarting.left - 1) }, 1000)
    return true
  } catch (e: any) { notify(e.message, 'error'); return false }
}
/** The live stream going down and coming back, while a restart is in the air. Returns true when that
    was the hub RETURNING, so the caller knows this link event has been spoken for.

    The guard is the whole of it: the brain answers the request and then waits a beat before it goes,
    so the link is still up when the tap finishes. Nothing counts as coming back until it has first
    gone away, or the overlay clears while the hub is still on its way down. */
export function restartLink(up: boolean): boolean {
  if (!store.restarting) return false
  if (!up) { store.restarting.lost = true; return false }
  if (!store.restarting.lost) return false
  /* Says how long it took, once and quietly: nobody should have to guess whether the restart they
     asked for actually happened, and a household that watches it take three minutes twice has
     learned something about their hardware. */
  const took = Math.max(1, Math.round((Date.now() - store.restarting.at) / 1000))
  const from = store.restarting.from
  store.restarting = null
  store.sheet = from
  clearInterval(restartTick)
  notify(took < 90 ? `Back. That took ${took} seconds.` : `Back. That took ${Math.round(took / 60)} minutes.`)
  return true
}

export function openWhy(roomId: string) { store.whyRoom = roomId; store.sheet = 'why' }
/** Pick up a conversation the house already has open, on the sheet that draws every other one. */
export function openFlow(flowId: string) { store.resume = flowId; store.sheet = 'add' }

/* ---------- setup and things found nearby ---------- */
/** True while the panel should show the setup flow instead of the house. */
export const needsSetup = () => !store.status || !store.status.setup_done   // once finished, an engine hiccup shows the calm offline note, not the welcome
export async function refreshStatus() {
  try { store.status = await getStatus() } catch { if (!store.status && !lock.unpaired) store.error = 'The hub is not answering.' }
}
export async function loadAccounts() {
  try { store.accounts = await getAccounts() } catch {}
}
/* Whether a thing is one the other apps can see, and whether it could be. The hub decides both --
   the kind has to be one this house shares and one the bridge can carry -- and the panel only ever
   asks about the device in front of somebody. docs/matter.md. */
export const canShare = (d: Device) => {
  const s = store.share
  /* The WHOLE kind, not cap()'s first word: a reading is `sensor.temperature` to the hub and cap()
     would hand it `sensor`, which is in nobody's list -- so every sensor would quietly say it cannot
     be shared while the hub was busy sharing it. */
  return !!s?.on && !!s.ready && s.kinds.includes(d.kind || d.guess || d.capability)
}
export const isShared = (d: Device) => canShare(d) && !(store.share?.left_out ?? []).includes(d.id)

export async function loadShare() {
  try { store.share = await getShare() } catch { /* an older hub: the door simply does not appear */ }
}
/* The phones this screen is allowed to know about, and the knocks it is allowed to answer -- which is
   not the same list on every phone in the house, so it is always the hub's answer to THIS phone rather
   than anything worked out here. A screen that holds no keys gets itself and no asks, and the pane that
   rises on asks therefore never rises on it.

   `tell` is the live nudge rather than a page load: say who just joined, and let the row of events know. */
export async function loadPhones(tell = false) {
  if (!store.status?.locked) { store.phones = []; store.asks = []; return }
  const known = new Set(store.phones.map(x => x.id))
  try { const p = await getPhones(); store.phones = p.phones; store.asks = p.asks } catch { return }
  if (!tell) return
  eventsSoon()
  for (const x of store.phones) if (!known.has(x.id) && !x.me && known.size) notify(`${x.name} joined the house.`)   // told on every screen that can see them; the newcomer already knows
}
/** May this screen decide who else gets in? The house's answer, in the row it keeps for this phone. */
export const holdsKeys = () => !store.status?.locked || ['setup', 'code'].includes(store.phones.find(p => p.me)?.how ?? '')
/* ---------- a bridge being set up ----------

   Asked for rather than streamed, because it only matters while somebody is standing there: the poll
   runs every couple of seconds while a bridge is mid-job and backs off to a minute when there is
   nothing to say. A hub with no bridge support at all answers 404 and the panel simply never shows
   the sheet -- that is why this swallows its errors instead of raising them. */
let bridgeTimer: number | undefined
export async function refreshBridge() {
  clearTimeout(bridgeTimer)
  try {
    store.bridge = await getBridge()
  } catch { store.bridge = null }
  const live = !!store.bridge && !['none', 'ready'].includes(store.bridge.state)
  bridgeTimer = window.setTimeout(refreshBridge, live ? 2000 : 60000)
}

let foundTimer: number | undefined
export async function refreshFound() {
  if (store.status?.driver !== 'ready') return
  try { store.found = await getDiscovered() } catch {}
}
function foundSoon() { clearTimeout(foundTimer); foundTimer = window.setTimeout(refreshFound, 2500) }

/* ---------- lifecycle ---------- */
function applyHome(h: Home) { store.rooms = h.rooms; store.entry = h.entry ?? []; store.homeName = h.name || ''; store.tempUnit = h.temp_unit || ''; store.loaded = true; store.error = ''; foundSoon(); if (store.homeName) document.title = store.homeName }
/** A room was set to a state by a rule or by another screen: keep the chip honest without a reload. */
function applyIntent(i: Intent) {
  const r = store.rooms.find(r => r.id === i.room)
  if (r) { r.intent = i.intent; r.set_by = i.set_by; r.hold_until = i.hold_until; eventsSoon() }
}
function applyDevice(d: Device) {
  for (const r of store.rooms) {
    const i = r.devices.findIndex(x => x.id === d.id)
    if (i >= 0) { r.devices[i] = d; delete store.pending[d.id]; if (store.viewer?.id === d.id) store.viewer = d; if (store.opened?.id === d.id) store.opened = d; eventsSoon(); return }
  }
}
let stop: (() => void) | undefined, lostTimer: number | undefined, skyTimer: number | undefined
export async function load() {
  await refreshStatus()
  if (lock.unpaired) return                    // the join screen is up; the house answers once this phone is in
  try { applyHome(await getHome()) } catch { store.error = 'The hub is not answering.' }
  loadAmbient(); loadRules(); loadRoutines(); loadAssistant(); loadPresence(); loadHealth(); loadSounds(); loadPhones(); loadAccounts(); loadShare()
}
let foundPoll: number | undefined
/* The hub came back on a different build from the one this page was reading. Until it reloads, the
   page IS the old build: the "Updated to" toast used to be the whole of it, and a wall or a phone kept
   running last week's panel against this week's brain until somebody thought to pull down on it.
   index.html is served no-cache and the assets are named by their hash, so a reload is the new panel
   and not a stale one. The moment is the right one too: a new version only ever arrives with the
   link coming back after the brain restarted, when the screen was saying "Updating the hub" or
   "Reconnecting" -- never under somebody's finger. The version is kept for the page that comes next,
   because a toast does not survive the reload and the screen should still say what happened. */
export function newBuild(was: string | undefined, now: string | undefined): boolean {
  return !!was && !!now && was !== now && now !== 'dev'
}
export function reloadOnto(version: string, took = 0) {
  try { sessionStorage.setItem('hub.updated', took ? `${version}|${took}` : version) } catch { /* a private window keeps nothing; the reload still happens */ }
  location.reload()
}
/** The page after the reload: say what the one before it saw, and how long it stood there.

    The figure is worth the words. A household that watched an update take four minutes twice has
    learned something about their own hardware, and it is the same figure the hub is now quoting back
    at them next time -- so the two had better agree. */
export function sayUpdated() {
  let v = ''
  try { v = sessionStorage.getItem('hub.updated') || ''; if (v) sessionStorage.removeItem('hub.updated') } catch { /* nothing kept */ }
  if (!v) return
  const [version, took] = v.split('|')
  const n = Number(took || 0)
  notify(n >= 5 ? `Updated to ${version}. That took ${n < 90 ? `${Math.round(n / 10) * 10} seconds` : `${Math.round(n / 60)} minutes`}.`
                : `Updated to ${version}.`)
}

export async function start() {
  await load()
  sayUpdated()
  if (lock.unpaired) { updateSky(); return }   // the sky still follows the clock; nothing to stream to until this phone is in, and rejoin() starts again
  updateSky(); clearInterval(skyTimer); skyTimer = window.setInterval(updateSky, 30000)
  clearInterval(foundPoll); foundPoll = window.setInterval(refreshFound, 60000)
  refreshBridge()
  stop = connect({ device: applyDevice, home: applyHome, intent: applyIntent, drafts: d => { store.drafts = d; eventsSoon() }, presence: p => { store.presence = p; eventsSoon() }, phones: () => loadPhones(true), share: () => { store.shareTick++; loadShare() }, ambient: a => { store.ambient = a; updateSky() }, status: s => {
    const was = store.status?.driver, version = store.status?.version
    store.status = s
    if (newBuild(version, s.version)) {
      const took = store.updating ? Math.round((Date.now() - store.updating.at) / 1000) : 0
      endUpdate(); reloadOnto(s.version!, took); return
    }
    /* An update nobody on this screen asked for -- the hub's own, at twenty to three, or somebody
       else's tap on another phone. The wall should say what is happening either way, and it can:
       the phase is in the status it just received. */
    const u = s.update
    if (u && (u.requested || u.state?.state === 'running')) beginUpdate(u.dark_seconds)
    else if (store.updating && u && !u.requested) endUpdate()
    if (s.driver === 'ready' && was !== 'ready') { load() }   // the engine just came up: read the house
  }, link: v => {
    store.linkUp = v
    clearTimeout(lostTimer)
    const back = restartLink(v)     // a restart this screen asked for, going or coming back
    updateLink(v)                   // ...and an update, which only ever needs to know it went
    if (v) {
      store.linkLost = false
      if (back) load()
      else if (store.restoring && store.linkLost === false && store.loaded) { store.restoring = false; notify('Restored. Welcome back.'); load() }
      else if (!store.loaded) load()
    }
    else lostTimer = window.setTimeout(() => (store.linkLost = true), 4000)   // a blink on startup is not worth a banner
  } })
}
export function halt() { stop?.(); clearInterval(skyTimer); clearInterval(foundPoll); clearTimeout(bridgeTimer) }
