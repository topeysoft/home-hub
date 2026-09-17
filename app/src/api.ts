import { request } from './code'
/* `capability` is the driver's word for what this is and it picks the Home Assistant service; `kind` is
   the owner's, where they have given one. Read the two together through cap() in store.ts, never the raw
   field: a lamp on a smart plug is a switch to the driver and a light to everybody who lives there. */
export type Device = { id: string; name: string; room_id: string; capability: string; state: string; attrs: Record<string, any>; hw?: string | null; own_room?: boolean; maker?: string | null; kind?: string | null }
export type Room = { id: string; name: string; devices: Device[]; intent: string; set_by?: string | null; hold_until?: number | null; motion_at?: number | null }
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
export type Update = { version: string; commit: string; channel: 'release' | 'main'; latest: { version: string; sha: string; when: string; title: string; what: string[] } | null; whats_new: ReleaseNotes | null; held: boolean; reached_us: boolean; available: boolean | null; offer: boolean | null; rejected: string | null; auto: boolean; verified: boolean; checked: number | null; requested: boolean; state: { state: 'running' | 'done' | 'failed' | 'reverted' | 'refused'; started?: number; finished?: number; commit?: string; to?: string; bad?: string; reverted?: boolean } | null; error: string | null }
export type Status = { driver: Driver; reason: string; setup_done: boolean; locked?: boolean; owner: string | null; home: string | null; location: boolean; rooms: number; devices: number; drivers: Part[]; problems?: Problem[]; version?: string; update?: Update }
/* One job on Needs a look. The brain writes every word of it, including the words on the buttons: the
   panel does not know what it is looking at, so it draws `acts` and invents nothing. `with` is what went
   quiet behind this one fault -- fix the fault and they all come back, which is why they are not lines of
   their own. See brain/hub/health.py. */
export type Act = { do: string; act: 'flow' | 'entry' | 'part' | 'check' | 'forget' | 'update'; to: string | null
  ask?: string        // a question to answer first, where the doing is worth a second's thought
  yes?: string }      // the words that answer it, with the name in them
export type Quiet = { id: string; name: string; where: string }
export type Note = { kind: 'offline' | 'storage' | 'driver' | 'update'; text: string; since: number | null; subject: string | null
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
export const setupOwner = (name: string, home: string) => post<Status>('/setup/owner', { name, home })
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
  unplaced?: number                        // of those, how many have no room yet
  waiting?: number                         // switches nearby that have never been let in (see addSwitch)
  bridges?: number                         // how many are set up and working, job or no job
  needs?: 'wifi'                           // failed because the hub has nothing to give: a hub on a cable does not know the house's Wi-Fi until told once
}
/* Letting a NEW switch in. A factory-fresh one will not join without the secret printed on its back,
   which is the mesh's own rule and not ours -- so the code has to be read off the thing itself, with
   a camera, and the wall panel has not got one. `code` is whatever the camera read, sent whole: the
   panel does not parse it, because what is in it is the bridge's business and it changes per maker.
   design/puck/Switch.dc.html (the wall hands over) and Scan.dc.html (the phone reads it). */
export type Letting = { state: 'working' | 'done' | 'failed'; text?: string; device_id?: string; name?: string }
export const addSwitch = (code: string) => post<Letting>('/bridge/switches', { code })
export const BRIDGE_STEPS = ['software', 'wifi', 'keys'] as const
export async function getBridge(): Promise<Bridge> { const r = await request('/bridge'); if (!r.ok) await fail(r); return r.json() }
/** Yes, that one is mine. The keys only go anywhere after this. */
export const adoptBridge = () => post<Bridge>('/bridge/adopt')
/** Not mine: stop offering it. It knocks again if it is unplugged and plugged back in. */
export const dismissBridge = () => post<Bridge>('/bridge/dismiss')
/** Leave it here -- the placing is over, whatever the signal says. */
export const placedBridge = () => post<Bridge>('/bridge/placed')
export const retryEntry = (entry_id: string) => post<Status>(`/setup/retry/${encodeURIComponent(entry_id)}`)
export const setCredentials = (handler: string, client_id: string, client_secret: string, hints?: Record<string, string>) => post<Step>('/credentials', { handler, client_id, client_secret, hints })
export const addRoom = (name: string) => post<{ id: string; name: string }>('/rooms', { name })
export const renameRoom = (id: string, name: string) => post(`/rooms/${encodeURIComponent(id)}/rename`, { name })
export const moveDevice = (id: string, room_id: string | null) => post(`/devices/${encodeURIComponent(id)}/move`, { room_id })
export const renameDevice = (id: string, name: string) => post(`/devices/${encodeURIComponent(id)}/rename`, { name })
/* Show this as. `offer` is what this thing may be shown as, its own kind included, computed by the brain
   from what the device can already serve -- a plug may be a lamp, and may not be a blind. It comes back
   empty where there is nothing to choose, and the pane then offers nothing at all. */
export type Kinds = { capability: string; kind: string; offer: string[]; words: Record<string, string>; why: string }
export async function getDeviceKinds(id: string): Promise<Kinds> {
  const r = await request(`/devices/${encodeURIComponent(id)}/kinds`); if (!r.ok) await fail(r); return r.json()
}
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
export type Routine = { id: string; name: string; room: string; when: Record<string, any>; if?: any[][]; then: Record<string, any>; enabled?: boolean; by?: string; said?: string; why?: string; noticed?: string; created?: number }
export type RoutineFile = { rules: Routine[]; drafts?: Routine[]; valid: boolean; errors: string[] }
export async function getRoutines(): Promise<RoutineFile> {
  const r = await request('/rules'); if (!r.ok) await fail(r); return r.json()
}
export const requestUpdate = () => post<Update>('/update')
/** Somebody opened This hub: look for a newer build now rather than at the hub's next look. Throttled on the brain. */
export const checkForUpdate = () => post<Update>('/update/check')
/** Whether the hub installs updates in the night on its own. */
export const setAutoUpdate = (auto: boolean) => post<Update>('/update/auto', { auto })
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
export function connect(on: { device: (d: Device) => void; home: (h: Home) => void; ambient: (a: Ambient) => void; status: (s: Status) => void; intent: (i: Intent) => void; drafts: (d: Routine[]) => void; presence: (p: Presence) => void; phones: () => void; link: (up: boolean) => void }) {
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
