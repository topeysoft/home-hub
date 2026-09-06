export type Device = { id: string; name: string; room_id: string; capability: string; state: string; attrs: Record<string, any> }
export type Room = { id: string; name: string; devices: Device[]; intent: string }
export type Home = { rooms: Room[] }
export type Weather = { id: string; condition: string; temperature: number | null; unit: string; humidity: number | null; wind_speed: number | null; wind_unit: string | null }
export type Ambient = { location: { lat: number; lon: number } | null; weather: Weather | null }
export type Event = { ts: number; kind: string; subject: string; old: string | null; new: string | null; source: string; detail: string | null }

const json = { 'Content-Type': 'application/json' }
async function fail(r: Response): Promise<never> {
  let detail = r.statusText
  try { detail = (await r.json()).detail ?? detail } catch {}
  throw new Error(detail)
}

export async function getHome(): Promise<Home> {
  const r = await fetch('/home'); if (!r.ok) await fail(r); return r.json()
}
export async function getAmbient(): Promise<Ambient> {
  const r = await fetch('/ambient'); if (!r.ok) await fail(r); return r.json()
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
export function connect(on: { device: (d: Device) => void; home: (h: Home) => void; ambient: (a: Ambient) => void; link: (up: boolean) => void }) {
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
    }
    ws.onclose = () => { on.link(false); if (!closed) setTimeout(open, delay = Math.min(delay * 2, 15000)) }
    ws.onerror = () => ws?.close()
  }
  open()
  return () => { closed = true; ws?.close() }
}
