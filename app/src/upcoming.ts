/* What the house will do next on its own: the soonest routine that runs by the clock or the sun. Idle-based ones
   ("after 20 minutes of nothing") have no time until something happens, so they stay out. */
import type { Routine } from './api'
import { store } from './store'
import { sunPosition } from './sun'

const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
function allowedDay(r: Routine, d: Date): boolean {
  for (const c of r.if ?? []) {
    if (!Array.isArray(c) || c[0] !== 'weekday') continue
    const key = DAYS[d.getDay()], [, op, val] = c
    if (op === 'in' && !(val as string[]).includes(key)) return false
    if (op === 'is' && val !== key) return false
    if (op === 'not' && val === key) return false
  }
  return true
}
/** The next sunrise or sunset after `from`, found by walking the day in two-minute steps. Null without a location. */
export function nextSun(from: Date, rise: boolean): Date | null {
  const loc = store.ambient.location; if (!loc) return null
  const H = -0.833
  let prev = sunPosition(from, loc.lat, loc.lon).elevation
  for (let i = 1; i <= 730; i++) {
    const d = new Date(from.getTime() + i * 120000)
    const el = sunPosition(d, loc.lat, loc.lon).elevation
    if (rise ? prev < H && el >= H : prev >= H && el < H) return d
    prev = el
  }
  return null
}
/** When a routine next fires, or null if it has no time of its own. */
export function nextRun(r: Routine, now: Date): Date | null {
  if (r.enabled === false) return null
  const w = r.when ?? {}
  if ('time' in w) {
    const [h, m] = String(w.time).split(':').map(Number)
    for (let day = 0; day < 8; day++) {
      const d = new Date(now); d.setDate(d.getDate() + day); d.setHours(h || 0, m || 0, 0, 0)
      if (d > now && allowedDay(r, d)) return d
    }
    return null
  }
  if ('sun' in w) {
    const off = (Number(w.offset) || 0) * 1000
    let from = new Date(now.getTime() - off)            // it fires at the event plus the offset, so look for events after now minus it
    for (let i = 0; i < 8; i++) {
      const ev = nextSun(from, w.sun !== 'set'); if (!ev) return null
      const at = new Date(ev.getTime() + off)
      if (allowedDay(r, at)) return at
      from = new Date(ev.getTime() + 60000)
    }
  }
  return null
}
export function upcoming(now = new Date()): { routine: Routine; at: Date } | null {
  let best: { routine: Routine; at: Date } | null = null
  for (const r of store.routines) { const at = nextRun(r, now); if (at && (!best || at < best.at)) best = { routine: r, at } }
  return best && best.at.getTime() - now.getTime() < 86400000 ? best : null
}
/** "Next: Living room lights on at dusk, 7:12 PM" — or '' when nothing is due in the coming day. */
export function upcomingLine(now = new Date()): string {
  const u = upcoming(now); if (!u) return ''
  const t = u.at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const today = u.at.toDateString() === now.toDateString()
  return `Next: ${u.routine.name}, ${today ? '' : 'tomorrow '}${t}`
}
