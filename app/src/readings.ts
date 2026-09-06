/* Sensors are read, not tapped: a room shows them as one line of readings above its tiles. */
import type { Device, Room } from './api'
import { cap, isDead, shortName } from './store'

export const isReading = (d: Device) => ['sensor', 'motion', 'contact'].includes(cap(d))
/** The words for what a sensor says right now. */
export function readingLabel(d: Device): string {
  if (isDead(d)) return 'Not responding'
  const k = cap(d)
  if (k === 'sensor') {
    const cls = d.capability.split('.')[1]
    const unit = cls === 'temperature' ? '°' : cls === 'humidity' ? '%' : cls === 'illuminance' ? ' lx' : ''
    const v = Number(d.state)
    return Number.isFinite(v) ? `${Math.round(v)}${unit}` : d.state
  }
  if (k === 'motion') return d.state === 'on' ? 'Motion' : 'No motion'
  if (k === 'contact') return d.state === 'on' ? 'Open' : 'Closed'
  return d.state
}
/** A sensor called "Motion" or "Sensor" has nothing to add to its reading; a named one ("Hallway", "Under the stairs") does. */
export function readingName(d: Device, room?: Room | null): string {
  const n = shortName(d, room)
  return /^((motion|sensor|detector|temperature)\s*)+$/i.test(n) && (cap(d) === 'motion' || d.capability === 'sensor.temperature') ? '' : n
}
/** Motion seen or a door open: the reading lights up. */
export const readingOn = (d: Device) => (cap(d) === 'motion' || cap(d) === 'contact') && d.state === 'on'
