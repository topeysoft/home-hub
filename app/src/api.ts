// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { request } from './code'
/* `capability` is the driver's word for what this is and it picks the Home Assistant service; `kind` is
   the owner's, where they have given one. Read the two together through cap() in store.ts, never the raw
   field: a lamp on a smart plug is a switch to the driver and a light to everybody who lives there. */
export type Device = { id: string; name: string; room_id: string; capability: string; state: string; attrs: Record<string, any>; hw?: string | null; own_room?: boolean; maker?: string | null; model?: string | null; entry?: string | null; kind?: string | null; guess?: string | null; hw_name?: string | null; named_by_unit?: boolean }
export type Room = { id: string; name: string; devices: Device[]; intent: string; set_by?: string | null; hold_until?: number | null; motion_at?: number | null; colors?: number[][] }   // colors: kept per room, [[hue, amount], …]
export type Intent = { room: string; intent: string; set_by: string | null; hold_until: number | null }
export type Home = { name?: string | null; temp_unit?: string; entry?: string[]; rooms: Room[] }   // entry: the rooms people come in through
export type Driver = 'down' | 'fresh' | 'needs-login' | 'connecting' | 'ready'
export type Part = { id: string; name: string; state: 'unknown' | 'off' | 'adding' | 'ready' | 'failed' | 'sign-in' | 'waiting'; text: string; port: number }
/* channel: which code this hub follows — 'release' (version tags, what a house runs) or 'main' (the
   branch, for a hub being worked on). `available` is null when the hub genuinely cannot tell, and
   `offer` is the same answer minus a version that was installed, would not start, and was put back:
   the hub stops raising that one on its own, and the button under This hub still installs it. */
/** What changed, in words a household reads. Written by hand into releases/<version>.md and shipped
   inside the brain's image, so these are the notes for the code this hub is actually running. */
export type ReleaseNotes = { version: string; what: string[]; details: string }
export type UpdateNotes = { notes: ReleaseNotes | null; history: ReleaseNotes[] }
export type Update = { version: string; commit: string; channel: 'release' | 'main'; latest: { version: string; sha: string; when: string; title: string; what: string[] } | null; whats_new: ReleaseNotes | null; held: boolean; reached_us: boolean; available: boolean | null; offer: boolean | null; rejected: string | null; auto: boolean; verified: boolean; checked: number | null; requested: boolean; state: { state: 'running' | 'done' | 'failed' | 'reverted' | 'refused'; started?: number; finished?: number; commit?: string; to?: string; bad?: string; reverted?: boolean } | null; error: string | null
  /* Where the host has got to, while it is getting there. The brain is alive for nearly all of an
     update -- the code, the signature and the pull all happen with it running -- so this is a real
     answer for most of the wait rather than a spinner. null when nothing is happening. */
  progress: UpdateProgress | null
  seconds: number        // how long an update takes in THIS house, measured rather than guessed
  dark_seconds: number   // ...and how much of that the wall is actually away for
}
export type UpdateProgress = {
  phase: 'checking' | 'fetching' | 'downloading' | 'building' | 'restarting' | 'proving' | 'putting_back'
  says: string           // the words for it, written in the brain: the panel decides none of them
  at: number | null; since: number
  dark: boolean          // the brain is not there to be asked during this one
  step: number | null; steps: number
  detail: string | null
  moving: string[] | null   // which containers this update really recreates, once the host has looked
  notices: string[]         // ...and what a household would notice about that, where there is anything
}
export type Status = { driver: Driver; reason: string; setup_done: boolean; locked?: boolean; owner: string | null; home: string | null; location: boolean; rooms: number; devices: number; drivers: Part[]; problems?: Problem[]; version?: string; update?: Update; language?: string }
/* One job on Needs a look. The brain writes every word of it, including the words on the buttons: the
   panel does not know what it is looking at, so it draws `acts` and invents nothing. `with` is what went
   quiet behind this one fault -- fix the fault and they all come back, which is why they are not lines of
   their own. See brain/hub/health.py. */
export type Act = { do: string; act: 'flow' | 'entry' | 'part' | 'check' | 'forget' | 'update' | 'restart' | 'bridge'; to: string | null
  ask?: string        // a question to answer first, where the doing is worth a second's thought
  yes?: string        // the words that answer it, with the name in them
  no?: string }       // ...and the ones that decline, where "Keep it" is not what is being kept
export type Quiet = { id: string; name: string; where: string }
export type Note = { kind: 'offline' | 'storage' | 'driver' | 'update' | 'restart' | 'bridge'; text: string; since: number | null; subject: string | null
  where?: string      // an offline thing: which room, and what sort of thing it is -- enough to go and look at it
  name?: string       // an offline thing: what it is called, apart from the sentence it is in
  with?: Quiet[]      // what went quiet with this fault
  acts?: Act[] }      // what can be done about it, in order
export type Found = { flow_id: string; handler: string; kind: string; title: string; source: string }
export type CatalogItem = { domain: string; name: string; brand?: string | null; local: boolean }
export type Field = { name: string; kind: 'text' | 'password' | 'number' | 'boolean' | 'select' | 'section'; label: string; hint: string; required: boolean; default: any; options?: { value: any; label: string }[]; fields?: Field[]; expanded?: boolean }
export type Problem = { entry_id: string; domain: string; title: string; state: string; reason: string }
export type Step = { flow_id: string | null; handler: string; kind: string; type: 'form' | 'menu' | 'abort' | 'create_entry' | 'progress' | 'external' | 'credentials'; step_id: string; title: string; description: string; last_step: boolean | null;
  errors?: Record<string, string>; fields?: Field[]; options?: { id: string; label: string }[]; reason?: string; hint?: string; retry?: boolean; entry_title?: string; progress?: string; url?: string; redirect_url?: string }
export type Weather = { id: string; condition: string; temperature: number | null; unit: string; humidity: number | null; wind_speed: number | null; wind_unit: string | null }
export type Place = { name: string; lat: number; lon: number; tz?: string | null }
/* look: how the panel looks, decided once by the house rather than per screen */
export type Look = { feel?: string; tone: string; layout: string; nav?: string; face?: string }
/* What is coming. Asked for rather than watched (brain/hub/forecast.py says why), and either half
   may be empty: plenty of integrations serve daily and refuse hourly. `rain` is a probability in
   per cent where the house has one, which is not everywhere. */
export type Hour = { at: string; condition: string; temperature: number | null; rain: number | null }
export type Day = { at: string; condition: string; high: number | null; low: number | null; rain: number | null }
export type Forecast = { hourly: Hour[]; daily: Day[] }
export type Ambient = { location: Place | null; weather: Weather | null; forecast?: Forecast | null; look?: Look }
export type Event = { ts: number; kind: string; subject: string; old: string | null; new: string | null; source: string; detail: string | null }
/* Who is home, as the brain sees it: null while it cannot tell (no people, no alarm). */
export type Presence = { somebody: boolean | null; since: number | null; source: 'people' | 'alarm' | null; people: { name: string; home: boolean | null }[]; alarm: string | null }
export async function getPresence(): Promise<Presence> {
  const r = await request('/presence'); if (!r.ok) await fail(r); return r.json()
}

const json = { 'Content-Type': 'application/json' }
async function fail(r: Response): Promise<never> {
  let detail = r.statusText, speak: Spoken | undefined
  /* `speak` rides along on a refusal as well as on an answer, and the 422 from /say is the reason:
     docs/voice.md has the house say "I didn't catch that" out loud ALWAYS, because silence there
     reads as being ignored. Every other caller sees the Error it has always seen. */
  try { const body = await r.json(); detail = body?.detail ?? detail; speak = body?.speak ?? undefined } catch {}
  throw Object.assign(new Error(detail), speak ? { speak } : {})
}

async function post<T = any>(url: string, body?: unknown): Promise<T> {
  const r = await request(url, { method: 'POST', headers: json, body: body === undefined ? undefined : JSON.stringify(body) }); if (!r.ok) await fail(r); return r.json()
}
export async function getStatus(): Promise<Status> {
  const r = await request('/setup/status'); if (!r.ok) await fail(r); return r.json()
}
/* The screen's own language rides along with the names. It is the last moment the engine's account
   can be given one -- Home Assistant takes it at onboarding and never asks again -- and nobody sets
   up a hub in order to answer a question about locales, so it is sent rather than asked for. */
export const setupOwner = (name: string, home: string) =>
  post<Status>('/setup/owner', { name, home, language: (() => { try { return navigator.language || 'en' } catch { return 'en' } })() })

/** The house's language, changed later from This hub. */
export const setLanguage = (language: string) => post<{ language: string }>('/language', { language })
export const setupLogin = (username: string, password: string) => post<Status>('/setup/login', { username, password })
export const setupHome = (name: string) => post<Status>('/setup/home', { name })
export const setupDone = () => post<Status>('/setup/done')
export const setPin = (pin: string) => post<Status>('/setup/pin', { pin })
export async function getAdvanced(): Promise<{ url: string; username: string | null; password: string | null }> {
  const r = await request('/setup/advanced'); if (!r.ok) await fail(r); return r.json()
}
export const checkDrivers = () => post<Status>('/setup/drivers')
export type Pair = { state: 'idle' | 'working' | 'listening' | 'found' | 'pin' | 'done' | 'failed' | 'closed'; kind?: string; text?: string; needs?: string | null; seconds_left?: number | null; device?: { id: any; name: string | null } | null }
export const startPair = (kind: string, code?: string) => post<Pair>('/pair', { kind, code })
export const pairPin = (pin: string) => post<Pair>('/pair/pin', { pin })
export async function getPair(): Promise<Pair> { const r = await request('/pair'); if (!r.ok) await fail(r); return r.json() }
export async function stopPair(): Promise<Pair> { const r = await request('/pair', { method: 'DELETE' }); if (!r.ok) await fail(r); return r.json() }
/* A BRIDGE is a small thing on a charger that brings in devices the hub has no radio of its own for --
   today the wall switches on the Brilliant mesh. It arrives one of two ways and the house says the same
   sentence either way: on the hub's cable (a bare one, which the hub also gives its software to) or over
   the air (one that already has it, and knocks). The panel draws this state and decides nothing; the
   screens are design/puck/Knock.dc.html and design/puck/Cable.dc.html.

   `state` is where the job is, not what the thing is:
     none      nothing to say
     knocking  one is offering itself and is blinking; nobody has let it in
     working   it is being set up, which is `step` and the ones before it
     placing   set up, and now in somebody's hand looking for a socket
     ready     it is somewhere, and `switches` came in with it
     failed    `text` says why, in the brain's words */
export type Bridge = {
  state: 'none' | 'knocking' | 'working' | 'placing' | 'ready' | 'failed'
  how?: 'cable' | 'air'
  step?: 'software' | 'wifi' | 'keys'
  text?: string
  switches?: number                        // how many it can hear from where it is
  signal?: 'strong' | 'weak' | 'none'
  quiet?: true                             // placing, and it has not been heard from at all for a while: probably a socket with no Wi-Fi
  unplaced?: number                        // of those, how many have no room yet
  waiting?: number                         // switches nearby that have never been let in (see addSwitch)
  bridges?: number                         // how many are set up and working, job or no job
  needs?: 'wifi'                           // failed because the hub has nothing to give: usually the password, since the host never hands a PSK back up
  ssid?: string                            // ...and the network the hub is standing on, when that is the one it wants the password for
  moving?: NetMove                         // every bridge being handed a new Wi-Fi at once (docs/network.md)
  /* The ones running older software than the house ships. A standing fact, not a job and not a
     fault: a bridge a version behind is a bridge doing its whole work. docs/puck-updates.md. */
  behind?: { chip: string; room: string | null; fw: string; latest: string; online: boolean }[]
}
/* THE NETWORK the house runs on -- the hub's own connection, and the Wi-Fi the bridges are given.
   Two questions, and on most hubs the answer is different: the hub is on a cable and the bridges are
   on the Wi-Fi, because they have no cable to be on. docs/network.md, drawn in design/network/.

   `how` is the hub itself:
     cable    on ethernet. The steadier way round, and the one the product recommends
     wifi     on `ssid`, at `signal`
     none     it has a radio and is on nothing
     unknown  nobody here can tell -- a hub whose machine has no network script (a laptop, a NAS)

   `bridges.checked` is the difference between a fact and a memory, and the panel must not blur it:
   true means the hub read that name off its own connection, false means somebody typed it once and
   nothing has verified it since. `known` false means the hub has the name and not the password --
   which happens the moment the hub moves and is exactly the bug this was built for. */
export type NetState = {
  how: 'cable' | 'wifi' | 'none' | 'unknown'
  ip: string
  name: string                             // the hub's own hostname, which is what a puck resolves
  ssid?: string
  signal?: 'strong' | 'ok' | 'faint'
  band?: string
  spare?: string                           // on a cable, but a Wi-Fi is configured behind it
  can_change: boolean                      // there is a radio AND something on the host that can drive it
  managed: boolean
  stale?: true                             // the host's picture has not been refreshed lately
  moving?: { ssid: string; since: number }  // the hub is being moved right now, and the host is watching it
  reverted?: string                        // ...and one did not take, so this is the name that failed
  bridges: { ssid: string; checked: boolean; known: boolean; count: number }
  bridges_moving?: NetMove | null          // the pucks' journey; `moving` above is the hub's own
}
/* A move, while it happens and after it. Rooms, never chip ids: a household knows where the hallway
   is and has never heard of c8ebba. `late` only appears once the hub has stopped waiting. */
export type NetMove = {
  state: 'moving' | 'done'
  ssid: string
  total: number
  followed: string[]
  waiting?: string[]
  late?: string[]
}
export type SeenNetwork = { ssid: string; signal?: 'strong' | 'ok' | 'faint'; band?: string | null; secure: boolean }
export async function getNetwork(): Promise<NetState> {
  const r = await request('/network'); if (!r.ok) await fail(r); return r.json()
}
export const scanNetworks = () => post<{ networks: SeenNetwork[]; can_change: boolean }>('/network/scan')
/* Move the bridges and leave the hub where it is -- the common case, and the safe one. */
export const moveBridges = (ssid: string, password: string) => post<NetMove>('/network/bridges', { ssid, password })
/* Move the hub as well. The brain tells the bridges FIRST and only then moves itself, so whichever
   arrives second finds the other already there; the host puts the old connection back if this hub
   never turns up on the new one. */
export const moveHub = (ssid: string, password: string) => post<NetState>('/network/hub', { ssid, password })
export const networkDone = () => post<Bridge>('/network/done')

/* Letting a NEW switch in, two ways, because a switch arrives in a hand or already screwed to a wall.

   WITH THE CODE on its back: `code` is whatever the camera read, sent whole -- the panel does not parse
   it, because what is in it is the bridge's business and changes per maker. A camera is the only way to
   read one and the wall panel has not got one, which is the whole of design/puck/Switch.dc.html (the
   wall hands over) and Scan.dc.html (the phone reads it).

   WITHOUT IT, because the code is behind the plate: the mesh never required that secret -- it is offered
   by these switches, not demanded. What the code really buys is knowing WHICH switch, so the codeless
   route has to prove that another way: ask the house what is waiting, make one of them announce itself,
   and let a person say whether the blinking one is the switch they just touched. No camera in any of it,
   so the wall can run the whole job on its own (design/puck/Held.dc.html and Waiting.dc.html). */
export type Letting = { state: 'working' | 'done' | 'failed'; text?: string; device_id?: string; name?: string }
export const addSwitch = (code: string) => post<Letting>('/bridge/switches', { code })
export const letSwitchIn = (uuid: string) => post<Letting>('/bridge/switches', { uuid })

/* One switch the bridge can hear. `state` is whose side it is on, and it decides what can be said:
     unclaimed  nobody owns it -- ready as it stands, whether it is fresh out of a box or just reset
     ours       already on this house, living under its light; nothing to do here
     other      on somebody else's network. THE one case where it has to be started over first */
export type Waiting = { state: 'unclaimed' | 'ours' | 'other'; rssi: number; addr: string; uuid?: string; net?: string }
export type Nearby = { state: 'done' | 'failed'; text?: string; waiting?: Waiting[]; claimed_elsewhere?: Waiting[] }
export async function nearbySwitches(): Promise<Nearby> {
  const r = await request('/bridge/nearby'); if (!r.ok) await fail(r); return r.json()
}
/* Make one announce itself. Without a code this is the ONLY thing that tells the switch somebody
   touched from any other unclaimed one in radio range, so a failure here is not cosmetic: it means
   the next question cannot honestly be asked. */
export const blinkSwitch = (uuid: string, seconds = 5) => post<{ state: string; text?: string }>('/bridge/blink', { uuid, seconds })
export const BRIDGE_STEPS = ['software', 'wifi', 'keys'] as const
/* The states that have nothing left to say once somebody has read them.
 *
 * The brain keeps reporting one until it is told, so a sheet that closes only its own copy goes away
 * and the very next poll brings it straight back. That was fixed for `failed` and the same bug then
 * sat in `ready` -- "It's in." reappeared every minute after a bridge was set up, and pressing Done
 * did nothing the hub could hear. The list lives here rather than in the sheet so the next state that
 * ends a job is added where the rest of the bridge's vocabulary is. */
export const BRIDGE_READ_ONCE = ['ready', 'failed'] as const
export const readOnce = (state?: string) => (BRIDGE_READ_ONCE as readonly string[]).includes(state ?? '')
export async function getBridge(): Promise<Bridge> { const r = await request('/bridge'); if (!r.ok) await fail(r); return r.json() }
/** Yes, that one is mine. The keys only go anywhere after this. */
export const adoptBridge = () => post<Bridge>('/bridge/adopt')
/** Not mine: stop offering it. It knocks again if it is unplugged and plugged back in. */
export const dismissBridge = () => post<Bridge>('/bridge/dismiss')
/** The house's Wi-Fi, told once: a hub on a cable has no other way to know it. Kept for every bridge after. */
export const bridgeWifi = (ssid: string, password: string) => post<Bridge>('/bridge/wifi', { ssid, password })

/* ---------- a light strip, knocking over Bluetooth ----------
 *
 * The same four beats as a bridge, in the same shell, with the same words -- design/strip/Spine.dc.html
 * is mostly a demonstration that a strip needs no new flow. What it does need is two questions in the
 * middle, and both exist for one reason: NOTHING CAN BE READ BACK OFF A STRIP. The data line is
 * write-only on every one of these parts, so neither the order its colors come out in nor how far it
 * goes can be detected. They are shown, and the household names what it can see.
 *
 * `asking` is which half of the color question is on screen. `lit` is how far the fill has got, which
 * the strip publishes as it goes -- the panel does not count, because the strip is the only thing that
 * knows how fast it is actually going. */
export type Strip = {
  state: 'none' | 'knocking' | 'working' | 'order' | 'length' | 'room' | 'ready' | 'failed'
  name?: string
  step?: 'wifi' | 'hub'                    // two, not the bridge's three: the software is already on it
  asking?: 'red' | 'which'
  /* Set when one of the two setup questions is being asked AGAIN about a strip that is already in --
     somebody cut it down, joined another on, or replaced it with a different make. The sheet says a
     different sentence for it, because somebody who came back already knows what the thing does. */
  revisit?: 'colors' | 'length'
  lit?: number                             // how many lights the fill has reached
  count?: number                           // ...and where it stopped
  order?: string                           // which of the six it turned out to be
  white?: boolean                          // it carries a separate white channel (the "stripes" answer)
  rooms?: { id: string; name: string }[]
  strips?: number                          // how many are set up and working, job or no job
  text?: string
  needs?: 'wifi'
}
/* Ending a job is the brain's to know, exactly as it is for a bridge: a sheet that closes only its
   own copy goes away and the next poll brings it straight back. */
export const STRIP_READ_ONCE = ['ready', 'failed'] as const
export const readStripOnce = (state?: string) => (STRIP_READ_ONCE as readonly string[]).includes(state ?? '')
export async function getStrip(): Promise<Strip> { const r = await request('/strip'); if (!r.ok) await fail(r); return r.json() }
/** Yes, that one is mine. Nothing of the house's moves before this. */
export const adoptStrip = () => post<Strip>('/strip/adopt')
/** Not mine. Needs no code -- refusing gives nothing away, and nothing was ever sent. */
export const dismissStrip = () => post<Strip>('/strip/dismiss')
export const stripWifi = (ssid: string, password: string) => post<Strip>('/strip/wifi', { ssid, password })
/** What the household can see on it: red, green, blue, stripes, or nothing at all. */
export const stripSaw = (saw: string) => post<Strip>('/strip/saw', { saw })
/** That's the whole of it. The strip latches where the fill had got to the instant it hears this. */
export const stripEnds = () => post<Strip>('/strip/ends')
export const stripAgain = () => post<Strip>('/strip/again')
export const stripRoom = (room: string) => post<Strip>('/strip/room', { room })
export const stripDone = () => post<Strip>('/strip/done')
/** Every strip the house has, for the rows that offer to ask one of them something again. */
export type StripRow = { id: string; online: boolean; count: number | null; order: string | null }
export async function listStrips(): Promise<{ strips: StripRow[] }> {
  const r = await request('/strip/list'); if (!r.ok) await fail(r); return r.json()
}
/** Ask a strip already in the house one of the two questions again. design/strip/Later.dc.html. */
export const revisitStrip = (id: string, what: 'colors' | 'length') =>
  post<Strip>('/strip/revisit', { id, what })
/* Take a bridge off the house. Offered only from the *Needs a look* line about one that has not come
   back, because it is the answer to a question the house asked first -- never a thing to go and find. */
/* ONE BRIDGE, as This hub lists it. Separate from `Bridge` above, which is the setting-up machine
   the sheet draws: this is the standing fact about a puck that is already in and working.
   `night` is null, not false, for a puck the hub has never heard speak -- "off" is a claim about a
   thing that has answered, and the card says "not heard from yet" instead of drawing a switch in a
   position nobody can vouch for. */
export type BridgeRow = {
  chip: string; room: string | null; where: string
  online: boolean; signal: 'strong' | 'weak' | 'none'
  switches: number; fw: string | null; behind: boolean; shipped: string | null
  night: boolean | null; level: number | null; lift: boolean
}
export async function listBridges(): Promise<{ bridges: BridgeRow[] }> {
  const r = await request('/bridge/list'); if (!r.ok) await fail(r); return r.json()
}
/* A bridge's own light. Leaving a field out means "do not touch it", which is what lets the card
   send one change at a time rather than restating the whole state on every tap. */
export const setBridgeLight = (chip: string, what: { night?: boolean; level?: number; lift?: boolean }) =>
  post<{ bridges: BridgeRow[] }>('/bridge/light', { chip, ...what })
export const forgetBridge = (chip: string) => post<{ forgotten: string }>('/bridge/forget', { chip })
/** Leave it here -- the placing is over, whatever the signal says. */
/* "Leave it here" -- and, when the sheet asked it, the answer to "leave its light on?" in the same
   call (docs/puck-light.md). Left out entirely rather than sent as false when nothing was asked: a
   bridge placed without an answer is a bridge with no nightlight, which is not the same thing as one
   whose household said no, and only the brain should be deciding what to do with the difference. */
export const placedBridge = (night?: boolean) =>
  post<Bridge>('/bridge/placed', night === undefined ? undefined : { night })
export const retryEntry = (entry_id: string) => post<Status>(`/setup/retry/${encodeURIComponent(entry_id)}`)
export const setCredentials = (handler: string, client_id: string, client_secret: string, hints?: Record<string, string>) => post<Step>('/credentials', { handler, client_id, client_secret, hints })
export const addRoom = (name: string) => post<{ id: string; name: string }>('/rooms', { name })
export const renameRoom = (id: string, name: string) => post(`/rooms/${encodeURIComponent(id)}/rename`, { name })
export const moveDevice = (id: string, room_id: string | null) => post(`/devices/${encodeURIComponent(id)}/move`, { room_id })
/** `unit` names the hardware this is part of, and its parts follow (docs/units.md). */
export const renameDevice = (id: string, name: string, unit = false) => post(`/devices/${encodeURIComponent(id)}/rename`, unit ? { name, unit } : { name })
/* Show this as. `offer` is what this thing may be shown as, its own kind included, computed by the brain
   from what the device can already serve -- a plug may be a lamp, and may not be a blind. It comes back
   empty where there is nothing to choose, and the pane then offers nothing at all. */
export type Kinds = { capability: string; kind: string; offer: string[]; words: Record<string, string>; why: string }
export async function getDeviceKinds(id: string): Promise<Kinds> {
  const r = await request(`/devices/${encodeURIComponent(id)}/kinds`); if (!r.ok) await fail(r); return r.json()
}
/** A fan with a light in it: which part is the tile. 'fan' is the default and clears the record (docs/units.md). */
export const setDeviceLead = (id: string, lead: 'fan' | 'light') => post<{ ok: boolean; leads: string }>(`/devices/${encodeURIComponent(id)}/lead`, { lead })
/** Say what a thing is. The driver's own word puts it back. */
export const setDeviceKind = (id: string, kind: string | null) => post<{ ok: boolean; kind: string }>(`/devices/${encodeURIComponent(id)}/kind`, { kind })
/* Every service the house has signed into: how it stands, and how much of the house came in with it.
   Three states and no more -- on, waiting to be signed into, or not answering. */
export type Account = { id: string; kind: string; name: string; state: 'on' | 'signin' | 'stopped'; why: string; flow: string | null; things: number }
export async function getAccounts(): Promise<Account[]> {
  const r = await request('/accounts'); if (!r.ok) await fail(r); return (await r.json()).accounts
}
export async function removeAccount(id: string) { const r = await request(`/accounts/${encodeURIComponent(id)}`, { method: 'DELETE' }); if (!r.ok) await fail(r) }

/* The end of a thing's life in the house: off whatever brought it, and out of the model with it. */
export async function forgetDevice(id: string) { const r = await request(`/devices/${encodeURIComponent(id)}`, { method: 'DELETE' }); if (!r.ok) await fail(r) }
export const setFan = (id: string, minutes: number) => post<{ ok: boolean; fan_until: number | null }>(`/devices/${encodeURIComponent(id)}/fan`, { minutes })
/** On now, off again in `minutes`; 0 cancels the timer and leaves it on. A plug, a lamp, a heater. */
export const runFor = (id: string, minutes: number) => post<{ ok: boolean; off_at: number | null }>(`/devices/${encodeURIComponent(id)}/timer`, { minutes })
export const setSense = (id: string, sensor: string | null) => post(`/devices/${encodeURIComponent(id)}/sense`, { sensor })
/* Ask a thing that has gone quiet whether it is there, and say what came back. A thing that is genuinely
   unplugged is still quiet afterwards, and saying so is the point: that is when removing it is the answer. */
export const checkDevice = (id: string) => post<{ ok: boolean; answering: boolean; text: string }>(`/devices/${encodeURIComponent(id)}/check`)
/** Make a thing blink so the person standing in the room can see which one the row is. The other half of
    "go and press one": pressing answers for what a hand can reach, this for eleven bulbs in a ceiling. */
export const identifyDevice = (id: string) => post<{ ok: boolean; text: string }>(`/devices/${encodeURIComponent(id)}/identify`)
/* Try a part of the driver layer again now, rather than waiting out its five-minute backoff. */
export const retryPart = (part_id: string) => post<{ ok: boolean; drivers: Part[] }>(`/drivers/${encodeURIComponent(part_id)}/retry`)
export async function getDiscovered(): Promise<Found[]> {
  const r = await request('/discovered'); if (!r.ok) await fail(r); return r.json()
}
export async function getCatalog(): Promise<CatalogItem[]> {
  const r = await request('/catalog'); if (!r.ok) await fail(r); return r.json()
}
export const startFlow = (handler: string) => post<Step>('/flows', { handler })
export const submitFlow = (id: string, data: Record<string, unknown>) => post<Step>(`/flows/${encodeURIComponent(id)}`, data)
export async function getFlow(id: string): Promise<Step> {
  const r = await request(`/flows/${encodeURIComponent(id)}`); if (!r.ok) await fail(r); return r.json()
}
export async function cancelFlow(id: string) { await request(`/flows/${encodeURIComponent(id)}`, { method: 'DELETE' }) }

export async function getHome(): Promise<Home> {
  const r = await request('/home'); if (!r.ok) await fail(r); return r.json()
}
export async function setLook(look: Partial<Look>): Promise<Look> {
  const r = await request('/look', { method: 'POST', headers: json, body: JSON.stringify(look) }); if (!r.ok) await fail(r); return r.json()
}
export async function getAmbient(): Promise<Ambient> {
  const r = await request('/ambient'); if (!r.ok) await fail(r); return r.json()
}
export async function searchPlaces(q: string): Promise<Place[]> {
  const r = await request(`/geo/search?q=${encodeURIComponent(q)}`); if (!r.ok) await fail(r); return r.json()
}
export async function autoLocate(): Promise<Place> {
  const r = await request('/geo/auto'); if (!r.ok) await fail(r); return r.json()
}
export async function placeName(lat: number, lon: number): Promise<Place> {
  const r = await request(`/geo/reverse?lat=${lat}&lon=${lon}`); if (!r.ok) await fail(r); return r.json()
}
export async function saveLocation(p: Place): Promise<{ ok: boolean; weather: string | null }> {
  const r = await request('/location', { method: 'POST', headers: json, body: JSON.stringify(p) }); if (!r.ok) await fail(r); return r.json()
}
export type Rules = Record<string, [string, string, Record<string, unknown>][]>
export async function getScenes(): Promise<Rules> {
  const r = await request('/scenes'); if (!r.ok) await fail(r); return r.json()
}
export async function getEvents(limit = 40): Promise<Event[]> {
  const r = await request(`/events?limit=${limit}`); if (!r.ok) await fail(r); return r.json()
}
/** What one thing has done, newest first: the foot of its opened pane. The log has always been able
    to answer this; nothing until now had a reason to ask. */
export async function getDeviceEvents(id: string, limit = 8): Promise<Event[]> {
  const r = await request(`/events?limit=${limit}&subject=${encodeURIComponent(id)}`); if (!r.ok) await fail(r); return r.json()
}
/** The last few times a room was set, held or shadowed, each with the rule's reasons. */
export async function getWhy(roomId: string, limit = 6): Promise<Event[]> {
  const r = await request(`/rooms/${encodeURIComponent(roomId)}/why?limit=${limit}`); if (!r.ok) await fail(r); return r.json()
}
/* Routines: the brain's rules.json, read whole and switched on or off one at a time. The panel never edits one here. */
export type Outcome = Record<string, any>
export type Routine = { id: string; name: string; room: string | string[]; when: Record<string, any>; if?: any[][]; then: Outcome | Outcome[]; enabled?: boolean; by?: string; said?: string; why?: string; noticed?: string; created?: number }
/* A routine's rooms and outcomes, always as lists. `room` is one id, "home", "entry" or several ids; `then`
   is one outcome or several run in order. Everything on the panel reads them through these two, so a rule
   that names three rooms is not a shape each caller has to remember to handle. */
export const roomsOf = (r: Routine): string[] => Array.isArray(r.room) ? r.room : [r.room]
export const outcomesOf = (r: Routine): Outcome[] => Array.isArray(r.then) ? r.then : r.then ? [r.then] : []
export type RoutineFile = { rules: Routine[]; drafts?: Routine[]; valid: boolean; errors: string[] }
export async function getRoutines(): Promise<RoutineFile> {
  const r = await request('/rules'); if (!r.ok) await fail(r); return r.json()
}
export const requestUpdate = () => post<Update>('/update')
/** Somebody opened This hub: look for a newer build now rather than at the hub's next look. Throttled on the brain. */
export const checkForUpdate = () => post<Update>('/update/check')
/** Whether the hub installs updates in the night on its own. */
export const setAutoUpdate = (auto: boolean) => post<Update>('/update/auto', { auto })
/* Turning it off and on again. Every word of the sheet is the brain's, the same way Needs a look's
   buttons are: what stops, what keeps working and how long it takes are all facts about THIS house
   and this hub, and a panel that wrote them itself would be guessing at all three. `rung` is the
   ladder in docs/restart.md -- the panel never picks one, it draws the one the hub chose and, once
   the hub says the same rung has stopped helping, the harder one underneath. */
export type Rung = 'hub' | 'everything' | 'machine'
export type RestartAsk = {
  rung: Rung; title: string; yes: string
  keeps: string          // what is still true while it is away -- the first line, and the one people are asking about
  stops: string[]        // ...and what is not, said only where it is true of this house
  flight: string[]       // what is half-done right now and will not survive
  seconds: number; how_long: string
  blocked: string | null // an update or a restore is running: no button, and this is why
  busy: boolean          // one is already going
  lately: number         // how many restarts somebody has asked for in the past hour
  harder: Rung | null    // the next rung up, once this one has stopped being the answer
  weary: string | null
  warn: string | null    // away, and about to restart the machine nobody is there to unplug
  may: boolean           // whether THIS phone may go through with it
}
/** What a restart at this rung would cost, in this house, right now. Open: a sheet that wanted the
    code before it would say what the button does is a sheet nobody reads. */
export async function askRestart(rung: Rung = 'hub'): Promise<RestartAsk> {
  const r = await request(`/restart?rung=${rung}`); if (!r.ok) await fail(r); return r.json()
}
/** Go. `understood` answers the one extra question an away phone is asked before the machine. */
export const doRestart = (rung: Rung, understood = false) =>
  post<{ rung: Rung; seconds: number; how_long: string }>('/restart', { rung, understood })

export type UpdateAsk = {
  version: string | null; title: string; yes: string
  what: string[]         // why this one, in the release's own words
  seconds: number; how_long: string
  dark_seconds: number; dark_how_long: string
  keeps: string          // the line an update may say more generously than a restart: downloading is not a blackout
  stops: string[]; flight: string[]
  blocked: string | null
  warn: string | null    // away, and nobody is home if it does not come back
  auto: boolean
}
/** What installing this update would cost, in this house, right now. Open, like the restart sheet. */
export async function askUpdate(): Promise<UpdateAsk> {
  const r = await request('/update/ask'); if (!r.ok) await fail(r); return r.json()
}
/** This build's notes and every release before it the image carries. */
export async function getUpdateNotes(): Promise<UpdateNotes> {
  const r = await request('/update/notes'); if (!r.ok) await fail(r); return r.json()
}
/** Somebody has read what's new; the card does not come back. */
export const markNotesRead = () => post<Update>('/update/notes/seen')
/** The house as one file, fetched with the code and handed to the browser as a download. */
export async function downloadBackup(): Promise<void> {
  const r = await request('/backup'); if (!r.ok) await fail(r)
  const name = /filename\*?=(?:UTF-8'')?"?([^";]+)/.exec(r.headers.get('content-disposition') ?? '')?.[1] ?? 'home-hub-backup.tar.gz'
  const url = URL.createObjectURL(await r.blob())
  const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 60000)
}
export async function restoreBackup(file: File): Promise<{ ok: boolean; manifest: { home?: string; owner?: string; made?: number; version?: string } }> {
  const r = await request('/restore', { method: 'POST', headers: { 'Content-Type': 'application/gzip' }, body: file }); if (!r.ok) await fail(r); return r.json()
}
export async function getHealth(): Promise<{ notes: Note[] }> {
  const r = await request('/health'); if (!r.ok) await fail(r); return r.json()
}
/* What happened while nobody was watching. Every word of this is the brain's, headings included:
   "Still on" is wrong over a door that is still unlocked, and the panel cannot know which it has.
   A finding is a SPAN -- "on for 10 hours" -- which is why there is no timestamp to format here. */
export type HappenedAct = { do: string; act: 'device' | 'room'; to: string; arg?: string }
export type HappenedItem = {
  kind: 'still' | 'over' | 'phone'; subject: string; text: string; when: string; ts: number
  where?: string        // which room and what sort of thing: enough to walk to it
  seconds?: number      // how long it has been that way; the sort order, already applied
  word?: string         // on | open | unlocked -- what the group heading was built from
  acts: HappenedAct[] } // empty on anything already over: there is nothing left to do about it
export type HappenedGroup = { id: 'still' | 'over' | 'people'; label: string; items: HappenedItem[] }
export type Happened = {
  lede: string; since: number; hint: string; empty: boolean
  away: { from?: number; to?: number | null }
  groups: HappenedGroup[] }
export async function getHappened(): Promise<Happened> {
  const r = await request('/happened'); if (!r.ok) await fail(r); return r.json()
}
/* Who changed what: behind the code, so `request` prompts for it on the 401 the way it does anywhere
   else. `named` is false when the house could not tell who it was -- never a guess. */
export type Change = { who: string; text: string; ts: number; named: boolean; when: string; kind: string; subject: string }
export type Changes = {
  rows: Change[]; coded_since: number | null; coded_when: string | null
  more: boolean }      // there is more behind this page: a list that stops at the limit looks like one that ended
export async function getChanges(limit = 200): Promise<Changes> {
  const r = await request(`/happened/changes?limit=${limit}`); if (!r.ok) await fail(r); return r.json()
}
export const setEntry = (rooms: string[]) => post<{ entry: string[] }>('/home/entry', { rooms })
export const enableRoutine = (id: string, enabled: boolean) => post<{ ok: boolean; enabled: boolean }>(`/rules/${encodeURIComponent(id)}/enable`, { enabled })
/* The assistant: it writes drafts and explains from the log. It has no call that changes a device. */
export type Assistant = { available: boolean; configured: boolean; source: 'panel' | 'env' | null; model: string }
export async function getAssistant(): Promise<Assistant> {
  const r = await request('/assistant'); if (!r.ok) await fail(r); return r.json()
}
export const setAssistantKey = (key: string) => post<Assistant>('/assistant/key', { key })
/** What the assistant hands back for a one-off request: one device, one action, confirmed by a person before it runs. */
export type Proposal = { kind: 'action'; device: string; device_name: string; action: string; data: Record<string, unknown>; name: string; said: string }
export const draftRoutine = (text: string) => post<Routine | Proposal>('/drafts', { text })
export type Sound = { id: string; name: string; ready: boolean }
export async function getSounds(): Promise<{ sounds: Sound[]; folder: string }> {
  const r = await request('/sounds'); if (!r.ok) await fail(r); return r.json()
}
export const approveDraft = (id: string) => post<Routine>(`/drafts/${encodeURIComponent(id)}/approve`)
export async function discardDraft(id: string) {
  const r = await request(`/drafts/${encodeURIComponent(id)}`, { method: 'DELETE' }); if (!r.ok) await fail(r)
}
export const explainRoom = (roomId: string, question: string) => post<{ question: string; answer: string }>(`/rooms/${encodeURIComponent(roomId)}/explain`, { question })
export async function act(id: string, action: string, data?: Record<string, unknown>) {
  const r = await request(`/devices/${encodeURIComponent(id)}/${action}`, { method: 'POST', headers: json, body: data ? JSON.stringify(data) : undefined })
  if (!r.ok) await fail(r)
}
/* A color somebody matched against this room's own lamps, kept so it is one tap next time.
   Per room rather than per lamp: it was tuned against the bulbs in there, and the bulb beside
   it is the same make more often than not. */
export async function keepColor(roomId: string, hue: number, amount: number): Promise<number[][]> {
  const r = await request(`/rooms/${encodeURIComponent(roomId)}/colors`, { method: 'POST', headers: json, body: JSON.stringify({ hue, amount }) })
  if (!r.ok) await fail(r)
  return (await r.json()).colors
}
export async function setIntent(roomId: string, state: string) {
  const r = await request(`/rooms/${encodeURIComponent(roomId)}/intent/${state}`, { method: 'POST' })
  if (!r.ok) await fail(r)
}
export async function setHomeIntent(state: string) {
  const r = await request(`/home/intent/${state}`, { method: 'POST' })
  if (!r.ok) await fail(r)
}
export const imageUrl = (id: string) => `/devices/${encodeURIComponent(id)}/image?t=${Date.now()}`

/** Live updates from the brain. Reconnects with backoff; reports link state. */
export function connect(on: { device: (d: Device) => void; home: (h: Home) => void; ambient: (a: Ambient) => void; status: (s: Status) => void; intent: (i: Intent) => void; drafts: (d: Routine[]) => void; presence: (p: Presence) => void; phones: () => void; share: () => void; link: (up: boolean) => void }) {
  let delay = 1000, ws: WebSocket | null = null, closed = false
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/stream`)
    ws.onopen = () => { delay = 1000; on.link(true) }
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data)
      if (m.type === 'device') on.device(m.device)
      else if (m.type === 'home') on.home(m.home)
      else if (m.type === 'ambient') on.ambient(m.ambient)
      else if (m.type === 'status') on.status(m.status)
      else if (m.type === 'intent') on.intent(m)
      else if (m.type === 'drafts') on.drafts(m.drafts)
      else if (m.type === 'presence') on.presence(m.presence)
      else if (m.type === 'phones') on.phones()   // a nudge, not the roster: what this phone may see is /phones' answer to ask for
      else if (m.type === 'share') on.share()    // the same shape: what is shared, and who holds it, is /share's answer to give
    }
    ws.onclose = () => { on.link(false); if (!closed) setTimeout(open, delay = Math.min(delay * 2, 15000)) }
    ws.onerror = () => ws?.close()
  }
  open()
  return () => { closed = true; ws?.close() }
}
/* The command box: one sentence in, one answer out. done and answer already happened (the grammar ran them, the way a tap
   does); action and rule are the assistant's proposals and have not. Driving the house never needs the code. */
export type Said = ({ kind: 'done'; text: string; said: string; count?: number } | { kind: 'answer'; text: string; said: string }
  | { kind: 'explain'; question: string; answer: string; said: string } | (Proposal & { said: string }) | (Routine & { kind: 'rule'; said: string })) & Answered
/* What the house would say out loud, and the clip on the hub that says it. Present only when the sentence
   ARRIVED by microphone and the room is awake — the route decides, not the kind (docs/voice.md). `spoken`
   is the sentence either way, which is what makes it something a test can read without an engine running. */
export type Spoken = { url: string; text: string }
type Answered = { spoken?: string; speak?: Spoken }
export const say = (text: string, room?: string | null, spoken = false) =>
  post<Said>('/say', { text, room: room ?? undefined, ...(spoken ? { spoken: true } : {}) })
/* Names and rooms for things under New devices: proposed by the house, then the assistant; nothing moves until Use is tapped. */
export type Suggestion = { id: string; name: string; room: string; why: string; source: 'house' | 'assistant' }
export async function getSuggestions(): Promise<{ items: Suggestion[]; assistant: boolean }> {
  const r = await request('/suggestions'); if (!r.ok) await fail(r); return r.json()
}
export async function getPhone(): Promise<{ ip: string }> {
  const r = await request('/phone'); if (!r.ok) await fail(r); return r.json()
}
export const qrUrl = (text: string) => `/qr.svg?text=${encodeURIComponent(text)}`

/* The phones that belong to the house, once it has a code. A phone gets in by typing the code, or by asking and being
   allowed from a screen that is already in; the hub keeps a hash and the phone a cookie, so removing one is instant. */
export type Phone = { id: string; name: string; kind: 'wall' | 'phone' | null; joined: number; expires: number | null; remote: boolean; last_seen: number | null; how: 'code' | 'wall' | 'setup'; me: boolean }
export type Ask = { id: string; name: string; kind: string | null; asked: number }
export type Me = { locked: boolean; paired: boolean; home: string; phone: Phone | null }
export async function getMe(): Promise<Me> { const r = await fetch('/phones/me'); if (!r.ok) await fail(r); return r.json() }
export async function getPhones(): Promise<{ phones: Phone[]; asks: Ask[] }> { const r = await request('/phones'); if (!r.ok) await fail(r); return r.json() }
export const askToJoin = (name: string) => post<Ask>('/phones/ask', { name })
export async function claimJoin(id: string): Promise<{ state: 'waiting' | 'allowed' | 'gone'; phone?: Phone }> { const r = await fetch(`/phones/claim/${encodeURIComponent(id)}`); if (!r.ok) await fail(r); return r.json() }
export const joinWithCode = (code: string, name: string) => post<{ ok: boolean; phone: Phone }>('/phones/code', { code, name })
export const allowPhone = (id: string, span: 'day' | 'weekend' | 'keep') => post<Phone>(`/phones/asks/${encodeURIComponent(id)}/allow`, { span })
export async function denyPhone(id: string) { const r = await request(`/phones/asks/${encodeURIComponent(id)}`, { method: 'DELETE' }); if (!r.ok) await fail(r) }
export async function removePhone(id: string) { const r = await request(`/phones/${encodeURIComponent(id)}`, { method: 'DELETE' }); if (!r.ok) await fail(r) }

/* Sharing the house outward, so Apple Home, Google Home and Alexa can see it: docs/matter.md.
   `offer` is the list of kinds this hub can publish, computed there and never typed here -- a panel
   that knows a kind the hub does not must not offer it, and one that does not know a kind the hub has
   must not hide it. `locks` is its own switch for its own reason, and is not in `kinds`. */
export type Holder = { index: number; name: string }
export type Share = {
  ready: boolean            // the installer left this hub a sharing key; without one there is nothing to switch on
  on: boolean
  kinds: string[]
  locks: boolean
  offer: string[]
  shared: number
  candidates: number       // what WOULD go out, so the off state can say something concrete
  left_out: string[]       // the ids the owner has kept home; the panel tests one device against it
  left_out_now: number     // how many of those are actually holding something back right now
  preview: { name: string; kind: string }[]   // a few of them by name, for the map at the top of the page
  holders: Holder[]
  open: boolean             // the door is open for an app to be added right now
  seconds_left: number | null
  code: string | null       // the printed code beside the QR, while the door is open
  bridge: { running?: boolean; commissioned?: boolean; stale?: boolean; error?: string | null } | null
}
export async function getShare(): Promise<Share> { const r = await request('/share'); if (!r.ok) await fail(r); return r.json() }
export const setShare = (body: { on?: boolean; kinds?: string[]; locks?: boolean }) => post<Share>('/share', body)
export const openShareWindow = () => post<Share>('/share/window', {})
/* One thing in or out by hand, from its own pane. Leaving a lamp out of the other apps is a change
   to the house, so it asks for the code the same way renaming and moving do. */
export const setDeviceShared = (id: string, shared: boolean) => post<Share>(`/devices/${encodeURIComponent(id)}/share`, { shared })
/* Its own route, not qrUrl(): that one carries an http address and checks it is one, and a Matter
   payload is MT:… . The cache-buster is because the code changes every time the door opens again. */
export const shareQrUrl = (n: number) => `/share/qr.svg?v=${n}`
