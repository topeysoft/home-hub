/* Words for what the house did on its own. Everything here is rendered from the event log and rules.json; no model. */
import type { Event, Room, Routine } from './api'
import { store, LABELS, deviceById, routineById, cap } from './store'

const cap1 = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const label = (s: string | null | undefined, home = false) => home && s === 'asleep' ? 'Bedtime' : LABELS[s ?? ''] ?? (s && s !== 'unknown' ? cap1(s) : 'Set')
export const placeName = (id: string) => id === 'home' ? 'the whole house' : id === 'entry' ? 'where you come in' : `the ${store.rooms.find(r => r.id === id)?.name ?? id}`
const devName = (id: string | undefined) => (id && deviceById(id)?.name) || 'something'

/* ---------- time, said plainly ---------- */
export function dur(s: number): string {
  if (s < 60) return s === 1 ? 'a second' : `${s} seconds`
  if (s < 3600) { const m = Math.round(s / 60); return m === 1 ? 'a minute' : `${m} minutes` }
  const h = s / 3600
  if (Number.isInteger(h)) return h === 1 ? 'an hour' : `${h} hours`
  return `${Math.round(s / 60)} minutes`
}
/** How long a hold has left, or '' once it has passed. */
export function left(until: number | null | undefined, now = Date.now()): string {
  if (!until) return ''
  const s = until - now / 1000
  if (s <= 0) return ''
  if (s < 60) return 'under a minute'
  if (s < 3600) return `${Math.round(s / 60)} min`
  const h = Math.floor(s / 3600), m = Math.round((s - h * 3600) / 60)
  return m ? `${h} h ${m} min` : `${h} h`
}
const at = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
export function clock(hhmm: string): string {
  const [h, m] = String(hhmm).split(':').map(Number)
  const d = new Date(); d.setHours(h || 0, m || 0, 0, 0)
  return d.toLocaleTimeString([], m ? { hour: 'numeric', minute: '2-digit' } : { hour: 'numeric' })
}
export function whenText(ts: number, now = Date.now()): string {
  const d = new Date(ts * 1000), t = at(ts)
  const today = new Date(now); today.setHours(0, 0, 0, 0)
  if (d.getTime() >= today.getTime()) return t
  if (d.getTime() >= today.getTime() - 86400000) return `Yesterday, ${t}`
  return `${d.toLocaleDateString([], { weekday: 'short' })}, ${t}`
}

/* ---------- the rule vocabulary, in sentences ---------- */
const DAY: Record<string, string> = { mon: 'Mondays', tue: 'Tuesdays', wed: 'Wednesdays', thu: 'Thursdays', fri: 'Fridays', sat: 'Saturdays', sun: 'Sundays' }
const list = (xs: string[]) => xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]

/** A trigger as words: in the present for a routine ("when there's motion"), in the past for what set a room ("motion in the room"). */
export function triggerWords(w: Record<string, any> | undefined, past: boolean): string {
  if (!w) return ''
  if ('motion' in w) return past ? 'motion in the room' : "when there's motion"
  if ('contact' in w) return past ? `${devName(w.device)} ${w.contact === 'open' ? 'opened' : 'closed'}` : `when a door or window ${w.contact === 'open' ? 'opens' : 'closes'}`
  if ('idle' in w) return past ? `no motion for ${dur(w.idle)}` : `after ${dur(w.idle)} of nothing`
  if ('time' in w) return `at ${clock(w.time)}`
  if ('sun' in w) { const o = Number(w.offset) || 0, ev = w.sun === 'set' ? 'sunset' : 'sunrise'; return o ? `${dur(Math.abs(o))} ${o < 0 ? 'before' : 'after'} ${ev}` : `at ${ev}` }
  if ('presence' in w) return (w.presence === 'nobody' ? (past ? 'everyone had left' : 'when everyone has left') : (past ? 'someone came home' : 'when someone comes home')) + (w.for ? ` for ${dur(w.for)}` : '')
  if ('intent' in w) return `${past ? '' : 'when '}${cap1(w.in ? placeName(w.in) : 'a room')} ${past ? 'was' : 'is'} set to ${label(w.intent, w.in === 'home')}`
  if ('device' in w) return `${past ? '' : 'when '}${devName(w.device)} ${past ? 'went' : 'goes'} ${w.state}`
  return ''
}
/** A condition as words. Works on a rule's [subject, op, value] and on the log's [..., actual, ok] alike. */
export function condWords(c: any[]): string {
  if (!Array.isArray(c) || c.length < 3) return ''
  const [subject] = c
  if (subject === 'device') { const [, id, op, val] = c.length >= 6 || c.length === 4 ? c : [c[0], c[1], 'is', c[2]]; return `${op === 'not' ? 'unless' : 'while'} ${devName(id)} is ${val}` }
  const [, op, val] = c
  if (subject === 'sun') { const deg = Number.isFinite(Number(val)) ? Number(val) : 0; return op === 'below' ? (deg <= 0 ? 'after dark' : `with the sun below ${deg}°`) : op === 'above' ? (deg >= 0 ? 'in daylight' : `with the sun above ${deg}°`) : '' }
  if (subject === 'time') return op === 'between' ? `between ${clock(val[0])} and ${clock(val[1])}` : op === 'below' ? `before ${clock(val)}` : op === 'above' ? `after ${clock(val)}` : ''
  if (subject === 'weekday') return op === 'in' ? `on ${list((val as string[]).map(d => DAY[d] ?? d))}` : op === 'is' ? `on ${DAY[val] ?? val}` : op === 'not' ? `except ${DAY[val] ?? val}` : ''
  if (subject === 'intent') return op === 'not' ? `unless the room is on ${label(val)}` : `while the room is on ${label(val)}`
  if (subject === 'home') return op === 'not' ? `unless the house is on ${label(val, true)}` : `while the house is on ${label(val, true)}`
  if (subject === 'presence') return val === 'nobody' ? 'when nobody is home' : 'when someone is home'
  if (subject === 'light') return op === 'below' ? 'when it is dim inside' : 'when it is bright inside'
  return ''
}
function outcomeWords(r: Routine): string {
  const th = r.then
  if ('intent' in th) return r.room === 'home' ? `Sets the whole house to ${label(th.intent, true)}.` : r.room === 'entry' ? `Sets those rooms to ${label(th.intent)}.` : `Sets the room to ${label(th.intent)}.`
  if ('device' in th) return `${cap1(devName(th.device))}: ${th.action}.`
  if ('notify' in th) return `Sends a note: “${th.notify}”.`
  return ''
}
/** One line under a routine's name: "When there's motion, after dark. Sets the room to Here." */
export function routineWords(r: Routine): string {
  const head = [triggerWords(r.when, false), ...(r.if ?? []).map(condWords)].filter(Boolean).join(', ')
  return [head ? cap1(head) + '.' : '', outcomeWords(r)].filter(Boolean).join(' ')
}
function triggerIcon(w: Record<string, any> | undefined): string {
  if (!w) return 'sparkle'
  if ('motion' in w) return 'motion'
  if ('contact' in w) return 'contact'
  if ('idle' in w || 'time' in w) return 'clock'
  if ('sun' in w) return 'sun'
  if ('presence' in w) return 'home'
  if ('device' in w) { const d = deviceById(w.device); return d ? cap(d) : 'switch' }
  return 'sparkle'
}

/* ---------- the line on a room: who set it, and for how long a hand keeps routines away ---------- */
export function setByLine(room: Room, now = Date.now()): { icon: string; text: string } | null {
  const l = left(room.hold_until, now), state = label(room.intent)
  if (room.set_by?.startsWith('rule:')) return { icon: 'sparkle', text: `${state} · by a routine` }
  if (room.set_by === 'user') return { icon: 'check', text: `${state} · by hand${l ? `, ${l} left` : ''}` }
  if (l) return { icon: 'check', text: `Used by hand · routines stay out for ${l}` }
  return null
}

/* ---------- one log row, as a sentence a person would say ---------- */
export function explain(ev: Event): { icon: string; text: string; sub: string } {
  let d: any = {}; try { d = ev.detail ? JSON.parse(ev.detail) : {} } catch {}
  const home = ev.subject === 'home', r = d.rule ? routineById(d.rule) : undefined
  const name = r?.name ?? (d.rule ? 'A routine that has since been removed' : 'A routine')
  const want = label(ev.new, home)
  if (ev.kind === 'intent' && ev.source === 'rule') {
    const bits = [triggerWords(d.trigger, true), ...((d.checked ?? []) as any[][]).map(condWords)].filter(Boolean)
    const failed = d.failed?.length ? ` · ${d.failed.length === 1 ? 'one thing' : `${d.failed.length} things`} didn't respond` : ''
    return { icon: triggerIcon(d.trigger), text: cap1(name), sub: `${home ? 'The whole house' : 'The room'} went to ${want}${bits.length ? ' · ' + bits.join(' · ') : ''}${failed}` }
  }
  if (ev.kind === 'intent') {
    if (ev.source === 'user') return { icon: 'check', text: home ? `The whole house set to ${want} by hand` : `Set to ${want} by hand`, sub: 'Chosen on a panel or phone. Routines leave the room alone for a while after that.' }
    return { icon: 'sparkle', text: `${home ? 'The whole house' : 'The room'} went to ${want}`, sub: `By the hub itself.` }
  }
  if (ev.kind === 'held') return { icon: 'lock', text: `A routine wanted ${want} but left the room alone`, sub: `${cap1(name)} · someone had used the room by hand${d.until ? `, so it waits until ${at(d.until)}` : ''}` }
  if (ev.kind === 'shadowed') return { icon: 'sparkle', text: `A routine wanted ${want} but another got there first`, sub: cap1(name) }
  if (ev.kind === 'failed') return { icon: 'refresh', text: "A routine tried but something didn't respond", sub: `${cap1(name)} · ${ev.new ?? ''}`.trim() }
  return { icon: 'sparkle', text: `${home ? 'The whole house' : 'The room'} changed`, sub: ev.kind }
}
