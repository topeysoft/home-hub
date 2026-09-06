import { reactive } from 'vue'
import { getHome, connect, type Room, type Device, type Home } from './api'

export const store = reactive({ rooms: [] as Room[], linkUp: false, error: '', loaded: false })

const ACTIVE = new Set(['on', 'playing', 'open', 'unlocked', 'cleaning', 'streaming', 'recording'])
export const isActive = (d: Device) => ACTIVE.has(d.state)
export const cap = (d: Device) => d.capability.split('.')[0]
export const visibleRooms = () => store.rooms.filter(r => r.id !== 'unassigned' || r.devices.length)

/** One line describing what is happening in a room. Written for a person, not a log. */
export function activity(r: Room): string {
  const parts: string[] = []
  const lights = r.devices.filter(d => cap(d) === 'light' && d.state === 'on').length
  if (lights) parts.push(lights === 1 ? '1 light on' : `${lights} lights on`)
  for (const d of r.devices.filter(d => cap(d) === 'media' && d.state === 'playing'))
    parts.push(d.attrs.media_title ? `${d.attrs.media_title}` : `${d.name} playing`)
  const open = r.devices.filter(d => cap(d) === 'cover' && d.state === 'open').length
  if (open) parts.push(open === 1 ? 'blind open' : `${open} blinds open`)
  if (r.devices.some(d => cap(d) === 'lock' && d.state === 'unlocked')) parts.push('unlocked')
  if (r.devices.some(d => cap(d) === 'motion' && d.state === 'on')) parts.push('motion')
  return parts.length ? parts.join(' · ') : r.devices.length ? 'Quiet' : 'Nothing here yet'
}

export function roomActive(r: Room) { return r.devices.some(d => isActive(d) && cap(d) !== 'camera') }

function applyHome(h: Home) { store.rooms = h.rooms; store.loaded = true }
function applyDevice(d: Device) {
  for (const r of store.rooms) {
    const i = r.devices.findIndex(x => x.id === d.id)
    if (i >= 0) { r.devices[i] = d; return }
  }
}

let stop: (() => void) | undefined
export async function start() {
  try { applyHome(await getHome()); store.error = '' } catch { store.error = 'The hub is not answering.' }
  stop = connect({ device: applyDevice, home: applyHome, link: v => (store.linkUp = v) })
}
export function halt() { stop?.() }
