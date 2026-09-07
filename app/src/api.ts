import { request } from './code'
export type Device = { id: string; name: string; room_id: string; capability: string; state: string; attrs: Record<string, any>; hw?: string | null; own_room?: boolean }
export type Room = { id: string; name: string; devices: Device[]; intent: string; set_by?: string | null; hold_until?: number | null; motion_at?: number | null }
export type Intent = { room: string; intent: string; set_by: string | null; hold_until: number | null }
export type Home = { name?: string | null; temp_unit?: string; entry?: string[]; rooms: Room[] }   // entry: the rooms people come in through
export type Driver = 'down' | 'fresh' | 'needs-login' | 'connecting' | 'ready'
export type Part = { id: string; name: string; state: 'unknown' | 'off' | 'adding' | 'ready' | 'failed' | 'sign-in' | 'waiting'; text: string; port: number }
export type Update = { version: string; commit: string; latest: { sha: string; when: string; title: string } | null; available: boolean | null; checked: number | null; requested: boolean; state: { state: 'running' | 'done' | 'failed'; started?: number; finished?: number; commit?: string } | null; error: string | null }
export type Status = { driver: Driver; reason: string; setup_done: boolean; locked?: boolean; owner: string | null; home: string | null; location: boolean; rooms: number; devices: number; drivers: Part[]; problems?: Problem[]; version?: string; update?: Update }
export type Note = { kind: 'offline' | 'storage' | 'driver' | 'update'; text: string; since: number | null; subject: string | null }
export type Found = { flow_id: string; handler: string; kind: string; title: string; source: string }
export type CatalogItem = { domain: string; name: string; brand?: string | null; local: boolean }
export type Field = { name: string; kind: 'text' | 'password' | 'number' | 'boolean' | 'select' | 'section'; label: string; hint: string; required: boolean; default: any; options?: { value: any; label: string }[]; fields?: Field[]; expanded?: boolean }
export type Problem = { entry_id: string; domain: string; title: string; state: string; reason: string }
export type Step = { flow_id: string | null; handler: string; kind: string; type: 'form' | 'menu' | 'abort' | 'create_entry' | 'progress' | 'external' | 'credentials'; step_id: string; title: string; description: string; last_step: boolean | null;
  errors?: Record<string, string>; fields?: Field[]; options?: { id: string; label: string }[]; reason?: string; hint?: string; retry?: boolean; entry_title?: string; progress?: string; url?: string; redirect_url?: string }
export type Weather = { id: string; condition: string; temperature: number | null; unit: string; humidity: number | null; wind_speed: number | null; wind_unit: string | null }
export type Place = { name: string; lat: number; lon: number; tz?: string | null }
export type Ambient = { location: Place | null; weather: Weather | null }
export type Event = { ts: number; kind: string; subject: string; old: string | null; new: string | null; source: string; detail: string | null }
/* Who is home, as the brain sees it: null while it cannot tell (no people, no alarm). */
export type Presence = { somebody: boolean | null; since: number | null; source: 'people' | 'alarm' | null; people: { name: string; home: boolean | null }[]; alarm: string | null }
export async function getPresence(): Promise<Presence> {
  const r = await request('/presence'); if (!r.ok) await fail(r); return r.json()
}

const json = { 'Content-Type': 'application/json' }
async function fail(r: Response): Promise<never> {
  let detail = r.statusText
  try { detail = (await r.json()).detail ?? detail } catch {}
  throw new Error(detail)
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
export const retryEntry = (entry_id: string) => post<Status>(`/setup/retry/${encodeURIComponent(entry_id)}`)
export const setCredentials = (handler: string, client_id: string, client_secret: string, hints?: Record<string, string>) => post<Step>('/credentials', { handler, client_id, client_secret, hints })
export const addRoom = (name: string) => post<{ id: string; name: string }>('/rooms', { name })
export const renameRoom = (id: string, name: string) => post(`/rooms/${encodeURIComponent(id)}/rename`, { name })
export const moveDevice = (id: string, room_id: string | null) => post(`/devices/${encodeURIComponent(id)}/move`, { room_id })
export const renameDevice = (id: string, name: string) => post(`/devices/${encodeURIComponent(id)}/rename`, { name })
export const setFan = (id: string, minutes: number) => post<{ ok: boolean; fan_until: number | null }>(`/devices/${encodeURIComponent(id)}/fan`, { minutes })
export const setSense = (id: string, sensor: string | null) => post(`/devices/${encodeURIComponent(id)}/sense`, { sensor })
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
export function connect(on: { device: (d: Device) => void; home: (h: Home) => void; ambient: (a: Ambient) => void; status: (s: Status) => void; intent: (i: Intent) => void; drafts: (d: Routine[]) => void; presence: (p: Presence) => void; link: (up: boolean) => void }) {
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
    }
    ws.onclose = () => { on.link(false); if (!closed) setTimeout(open, delay = Math.min(delay * 2, 15000)) }
    ws.onerror = () => ws?.close()
  }
  open()
  return () => { closed = true; ws?.close() }
}
/* The command box: one sentence in, one answer out. done and answer already happened (the grammar ran them, the way a tap
   does); action and rule are the assistant's proposals and have not. Driving the house never needs the code. */
export type Said = { kind: 'done'; text: string; said: string; count?: number } | { kind: 'answer'; text: string; said: string }
  | { kind: 'explain'; question: string; answer: string; said: string } | (Proposal & { said: string }) | (Routine & { kind: 'rule'; said: string })
export const say = (text: string, room?: string | null) => post<Said>('/say', { text, room: room ?? undefined })
/* Names and rooms for things under New devices: proposed by the house, then the assistant; nothing moves until Use is tapped. */
export type Suggestion = { id: string; name: string; room: string; why: string; source: 'house' | 'assistant' }
export async function getSuggestions(): Promise<{ items: Suggestion[]; assistant: boolean }> {
  const r = await request('/suggestions'); if (!r.ok) await fail(r); return r.json()
}
export async function getPhone(): Promise<{ ip: string }> {
  const r = await request('/phone'); if (!r.ok) await fail(r); return r.json()
}
export const qrUrl = (text: string) => `/qr.svg?text=${encodeURIComponent(text)}`
