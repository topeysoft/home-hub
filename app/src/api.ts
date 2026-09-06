export type Device = { id: string; name: string; room_id: string; capability: string; state: string; attrs: Record<string, any> }
export type Room = { id: string; name: string; devices: Device[]; intent: string; set_by?: string | null; hold_until?: number | null; motion_at?: number | null }
export type Intent = { room: string; intent: string; set_by: string | null; hold_until: number | null }
export type Home = { name?: string | null; rooms: Room[] }
export type Driver = 'down' | 'fresh' | 'needs-login' | 'connecting' | 'ready'
export type Part = { id: string; name: string; state: 'unknown' | 'off' | 'adding' | 'ready' | 'failed' | 'sign-in' | 'waiting'; text: string; port: number }
export type Status = { driver: Driver; reason: string; setup_done: boolean; owner: string | null; home: string | null; location: boolean; rooms: number; devices: number; drivers: Part[]; problems?: Problem[] }
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

const json = { 'Content-Type': 'application/json' }
async function fail(r: Response): Promise<never> {
  let detail = r.statusText
  try { detail = (await r.json()).detail ?? detail } catch {}
  throw new Error(detail)
}

async function post<T = any>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, { method: 'POST', headers: json, body: body === undefined ? undefined : JSON.stringify(body) }); if (!r.ok) await fail(r); return r.json()
}
export async function getStatus(): Promise<Status> {
  const r = await fetch('/setup/status'); if (!r.ok) await fail(r); return r.json()
}
export const setupOwner = (name: string, home: string) => post<Status>('/setup/owner', { name, home })
export const setupLogin = (username: string, password: string) => post<Status>('/setup/login', { username, password })
export const setupHome = (name: string) => post<Status>('/setup/home', { name })
export const setupDone = () => post<Status>('/setup/done')
export const checkDrivers = () => post<Status>('/setup/drivers')
export const retryEntry = (entry_id: string) => post<Status>(`/setup/retry/${encodeURIComponent(entry_id)}`)
export const setCredentials = (handler: string, client_id: string, client_secret: string, hints?: Record<string, string>) => post<Step>('/credentials', { handler, client_id, client_secret, hints })
export const addRoom = (name: string) => post<{ id: string; name: string }>('/rooms', { name })
export const renameRoom = (id: string, name: string) => post(`/rooms/${encodeURIComponent(id)}/rename`, { name })
export const moveDevice = (id: string, room_id: string | null) => post(`/devices/${encodeURIComponent(id)}/move`, { room_id })
export const renameDevice = (id: string, name: string) => post(`/devices/${encodeURIComponent(id)}/rename`, { name })
export async function getDiscovered(): Promise<Found[]> {
  const r = await fetch('/discovered'); if (!r.ok) await fail(r); return r.json()
}
export async function getCatalog(): Promise<CatalogItem[]> {
  const r = await fetch('/catalog'); if (!r.ok) await fail(r); return r.json()
}
export const startFlow = (handler: string) => post<Step>('/flows', { handler })
export const submitFlow = (id: string, data: Record<string, unknown>) => post<Step>(`/flows/${encodeURIComponent(id)}`, data)
export async function getFlow(id: string): Promise<Step> {
  const r = await fetch(`/flows/${encodeURIComponent(id)}`); if (!r.ok) await fail(r); return r.json()
}
export async function cancelFlow(id: string) { await fetch(`/flows/${encodeURIComponent(id)}`, { method: 'DELETE' }) }

export async function getHome(): Promise<Home> {
  const r = await fetch('/home'); if (!r.ok) await fail(r); return r.json()
}
export async function getAmbient(): Promise<Ambient> {
  const r = await fetch('/ambient'); if (!r.ok) await fail(r); return r.json()
}
export async function searchPlaces(q: string): Promise<Place[]> {
  const r = await fetch(`/geo/search?q=${encodeURIComponent(q)}`); if (!r.ok) await fail(r); return r.json()
}
export async function autoLocate(): Promise<Place> {
  const r = await fetch('/geo/auto'); if (!r.ok) await fail(r); return r.json()
}
export async function placeName(lat: number, lon: number): Promise<Place> {
  const r = await fetch(`/geo/reverse?lat=${lat}&lon=${lon}`); if (!r.ok) await fail(r); return r.json()
}
export async function saveLocation(p: Place): Promise<{ ok: boolean; weather: string | null }> {
  const r = await fetch('/location', { method: 'POST', headers: json, body: JSON.stringify(p) }); if (!r.ok) await fail(r); return r.json()
}
export type Rules = Record<string, [string, string, Record<string, unknown>][]>
export async function getScenes(): Promise<Rules> {
  const r = await fetch('/scenes'); if (!r.ok) await fail(r); return r.json()
}
export async function getEvents(limit = 40): Promise<Event[]> {
  const r = await fetch(`/events?limit=${limit}`); if (!r.ok) await fail(r); return r.json()
}
export async function act(id: string, action: string, data?: Record<string, unknown>) {
  const r = await fetch(`/devices/${encodeURIComponent(id)}/${action}`, { method: 'POST', headers: json, body: data ? JSON.stringify(data) : undefined })
  if (!r.ok) await fail(r)
}
export async function setIntent(roomId: string, state: string) {
  const r = await fetch(`/rooms/${encodeURIComponent(roomId)}/intent/${state}`, { method: 'POST' })
  if (!r.ok) await fail(r)
}
export async function setHomeIntent(state: string) {
  const r = await fetch(`/home/intent/${state}`, { method: 'POST' })
  if (!r.ok) await fail(r)
}
export const imageUrl = (id: string) => `/devices/${encodeURIComponent(id)}/image?t=${Date.now()}`

/** Live updates from the brain. Reconnects with backoff; reports link state. */
export function connect(on: { device: (d: Device) => void; home: (h: Home) => void; ambient: (a: Ambient) => void; status: (s: Status) => void; intent: (i: Intent) => void; link: (up: boolean) => void }) {
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
    }
    ws.onclose = () => { on.link(false); if (!closed) setTimeout(open, delay = Math.min(delay * 2, 15000)) }
    ws.onerror = () => ws?.close()
  }
  open()
  return () => { closed = true; ws?.close() }
}
