export type Device = { id: string; name: string; room_id: string; capability: string; state: string; attrs: Record<string, any> }
export type Room = { id: string; name: string; devices: Device[]; intent: string }
export type Home = { rooms: Room[] }

const json = { 'Content-Type': 'application/json' }

export async function getHome(): Promise<Home> {
  const r = await fetch('/home'); if (!r.ok) throw new Error(`home ${r.status}`); return r.json()
}
export async function act(id: string, action: string, data?: Record<string, unknown>) {
  const r = await fetch(`/devices/${encodeURIComponent(id)}/${action}`, { method: 'POST', headers: json, body: data ? JSON.stringify(data) : undefined })
  if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText)
}
export async function setIntent(roomId: string, state: string) {
  const r = await fetch(`/rooms/${encodeURIComponent(roomId)}/intent/${state}`, { method: 'POST' })
  if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText)
}

/** Live updates from the brain. Reconnects with backoff; reports link state. */
export function connect(on: { device: (d: Device) => void; home: (h: Home) => void; link: (up: boolean) => void }) {
  let delay = 1000, ws: WebSocket | null = null, closed = false
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/stream`)
    ws.onopen = () => { delay = 1000; on.link(true) }
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data)
      if (m.type === 'device') on.device(m.device)
      else if (m.type === 'home') on.home(m.home)
    }
    ws.onclose = () => { on.link(false); if (!closed) setTimeout(open, delay = Math.min(delay * 2, 15000)) }
    ws.onerror = () => ws?.close()
  }
  open()
  return () => { closed = true; ws?.close() }
}
