// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What an opened device says about itself.
 *
 * The pane is one shape for every kind — where and what, what you can do, one
 * reading, why it is like that, the instrument, and what it did today — and
 * only the instrument changes from a lamp to a mower. Everything in this file
 * is the part of that shape which is words rather than pixels, kept out of the
 * components so it can be read and tested in one place.
 *
 * The rule the whole file obeys: say only what the house actually knows. A
 * thermostat has a humidity because the brain keeps one; a lamp has no watts
 * and no protocol, so its pane does not have a row for them. Empty rows are
 * how a detail screen starts looking like a form.
 */
import type { Device, Event, Room } from './api'
import { cap, isDead, shortName, deviceById, LABELS } from './store'
import { partsOfMachine } from './machines'
import { readingLabel } from './readings'
import { whenText } from './why'

export type Fact = { k: string; v: string }
export type Verb = { id: 'power' | 'watch' | 'lamp' | 'fan' | 'why' | 'edit'; icon: string; label: string; primary?: boolean; on?: boolean }
export type Moment = { when: string; text: string }

const cap1 = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
/** What a reading is measured in, for the rows that quote it back. */
const sensorUnit = (d: Device, unit = '°') => {
  const cls = d.capability.split('.')[1]
  return cls === 'temperature' ? (unit || '°').replace(/[^°CF]/g, '') || '°' : cls === 'humidity' ? '%' : cls === 'illuminance' ? ' lx' : ''
}
const pct = (v: number) => `${Math.round(v)}%`
const bright = (d: Device) => d.attrs.brightness != null ? Math.round((d.attrs.brightness / 255) * 100) : null

/** Which instrument a device gets. Motion, a thermometer and a door contact share one: they have no
    verb, so what they are owed is the day they have had. */
export function paneKind(d: Device): string {
  const k = cap(d)
  return k === 'sensor' || k === 'motion' || k === 'contact' ? 'sense' : k
}

/* ---------- the one reading, large ---------- */
/** The single thing worth saying about this device in large type. For a player that is what is
    playing rather than the fact that it is playing: "The Bear", not "Playing". */
export function reading(d: Device, unit = '°'): string {
  if (isDead(d)) return 'Not answering'
  const k = cap(d), a = d.attrs, s = d.state
  const u = (unit || '°').replace(/[^°CF]/g, '') || '°'
  switch (k) {
    case 'light': {
      const b = bright(d)
      return s !== 'on' ? 'Off' : b != null ? pct(b) : 'On'
    }
    case 'switch': case 'appliance': return s === 'on' ? 'On' : 'Off'
    case 'machine': {   // a fridge says how many of its features are running, which is the one thing worth saying about it in large type
      const parts = partsOfMachine(d), on = parts.filter(p => p.state === 'on').length
      return !parts.length ? 'Nothing here' : !on ? 'Nothing on' : on === parts.length ? 'All on' : `${on} of ${parts.length} on`
    }
    case 'alarm': return s === 'on' ? 'Sounding' : 'Silent'
    case 'media': return a.media_title || (s === 'playing' ? 'Playing' : s === 'paused' ? 'Paused' : s === 'off' || s === 'standby' ? 'Off' : 'Idle')
    case 'climate': return a.current_temperature != null ? `${Math.round(a.current_temperature)}${u}` : s === 'off' ? 'Off' : cap1(s)
    case 'cover': return a.current_position != null && a.current_position > 0 && a.current_position < 100
      ? `${a.current_position}% open` : s === 'open' || a.current_position === 100 ? 'Open'
      : s === 'opening' ? 'Opening' : s === 'closing' ? 'Closing' : 'Shut'
    case 'lock': return s === 'locked' ? 'Locked' : s === 'unlocked' ? 'Unlocked' : cap1(s)
    case 'camera': return s === 'recording' ? 'Recording' : s === 'streaming' ? 'Live' : 'Quiet'
    case 'fan': return s === 'on' ? (a.percentage != null ? pct(a.percentage) : 'On') : 'Off'
    case 'vacuum': return s === 'cleaning' ? 'Out working' : s === 'returning' ? 'Heading back' : s === 'docked' ? 'Docked' : cap1(s)
    default: return readingLabel(d)          // a sensor says what the room strip says it says
  }
}

/* ---------- the verbs along the top ----------
   Never a blanket power button: the pane used to offer one to a lock, a blind, a camera and a
   mower, and the brain has no such action for any of the four -- pressing it answered 400. What a
   kind cannot do is not drawn. */
export function verbs(d: Device): Verb[] {
  const k = cap(d), out: Verb[] = []
  const on = d.state === 'on' || d.state === 'playing' || d.state === 'cleaning'
  if (k === 'light' || k === 'switch' || k === 'media' || k === 'fan' || k === 'appliance')   // never a machine: it has no one switch, its features are the instrument
    out.push({ id: 'power', icon: 'power', label: on ? 'Turn it off' : 'Turn it on', primary: true, on })
  /* Its own words, not "Turn it on". What this button does is make a noise the whole house hears,
     and a verb that says so is half of why the second tap is not a surprise. */
  if (k === 'alarm')
    out.push({ id: 'power', icon: 'alarm', label: on ? 'Silence it' : 'Sound it', primary: true, on })
  if (k === 'climate')
    out.push({ id: 'power', icon: 'power', label: d.state === 'off' ? 'Turn it on' : 'Turn it off', primary: true, on: d.state !== 'off' })
  if (k === 'camera') {
    out.push({ id: 'watch', icon: 'camera', label: 'Watch it', primary: true, on: true })
    if (d.attrs.light && deviceById(String(d.attrs.light))) out.push({ id: 'lamp', icon: 'light', label: 'Its floodlight', on: deviceById(String(d.attrs.light))?.state === 'on' })
  }
  /* a fan with a light in it: each part offers the other, whichever of them is the tile (units.ts) */
  if (k === 'fan' && d.attrs.light && deviceById(String(d.attrs.light))) out.push({ id: 'lamp', icon: 'light', label: 'Its light', on: deviceById(String(d.attrs.light))?.state === 'on' })
  if (k === 'light' && d.attrs.fan && deviceById(String(d.attrs.fan))) out.push({ id: 'fan', icon: 'fan', label: 'Its fan', on: deviceById(String(d.attrs.fan))?.state === 'on' })
  out.push({ id: 'why', icon: 'sparkle', label: 'Why is it like this' })
  out.push({ id: 'edit', icon: 'edit', label: 'Rename or move it' })
  return out
}

/* ---------- the three or four facts this thing actually knows ---------- */
export function facts(d: Device, room?: Room | null, unit = '°', events: Event[] = []): Fact[] {
  const k = cap(d), a = d.attrs, out: Fact[] = []
  const u = (unit || '°').replace(/[^°CF]/g, '') || '°'
  const add = (kk: string, v: string | number | null | undefined) => { if (v != null && v !== '') out.push({ k: kk, v: String(v) }) }
  if (k === 'light') add('Warmth', a.color_temp_kelvin ? `${a.color_temp_kelvin}K` : null)
  if (k === 'media') {
    const pos = Number(a.media_position), dur = Number(a.media_duration)
    if (Number.isFinite(pos) && Number.isFinite(dur) && dur > pos) add('Left', `${Math.max(1, Math.round((dur - pos) / 60))} min`)
    add('Volume', a.volume_level != null ? pct(a.volume_level * 100) : null)
    add('Playing on', a.app_name || a.source)
  }
  if (k === 'climate') {
    add('Humidity', a.current_humidity != null ? pct(a.current_humidity) : null)
    add('Asked for', a.temperature != null ? `${Math.round(a.temperature)}${u}` : null)
    add('Sensing', a.sense_from ? (a.sense_name || 'Another room') : 'Its own sensor')
  }
  if (k === 'fan') add('Speed', a.percentage != null ? pct(a.percentage) : null)
  if (k === 'cover') add('Open', a.current_position != null ? pct(a.current_position) : null)
  if (k === 'camera' && a.light) add('Floodlight', deviceById(String(a.light))?.state === 'on' ? 'On' : 'Off')
  if (a.motion) add('Motion sensor', deviceById(String(a.motion))?.state === 'on' ? 'Seeing motion' : 'Nobody about')   // built into the unit (units.ts)
  /* a machine's features are its instrument, and the rows there already say On and Off: not again here */
  if (k === 'fan' && a.light) add('Its light', deviceById(String(a.light))?.state === 'on' ? 'On' : 'Off')
  if (k === 'light' && a.fan) { const f = deviceById(String(a.fan)); add('Its fan', f ? (f.state === 'on' ? (f.attrs.percentage ? `${f.attrs.percentage}%` : 'On') : 'Off') : null) }

  /* A plug, a door and a mower carry almost nothing in their attributes -- which is why their panes
     used to be empty. What they do have is a day, and the log already keeps it. */
  if (events.length) {
    const on = spans(events)
    const last = (match: (e: Event) => boolean) => { const e = events.find(match); return e ? whenText(e.ts) : null }
    if (k === 'switch' || k === 'fan' || k === 'appliance') {
      add('On today', on.length ? forLong(on) : null)
      add('Last on', last(e => e.kind === 'state' && e.new === 'on'))
    }
    if (k === 'lock') {
      const opened = events.filter(e => e.new === 'unlocked' || e.new === 'unlock').length
      add('Opened today', opened ? `${opened} ${opened === 1 ? 'time' : 'times'}` : 'Not once')
      add('Last opened', last(e => e.new === 'unlocked' || e.new === 'unlock'))
    }
    if (k === 'vacuum') add('Last run', last(e => e.new === 'cleaning' || e.new === 'start'))
    /* the three that only watch: the reading is already the large line, so the facts are the shape
       of the day behind it */
    if (k === 'motion' || k === 'contact') {
      const times = events.filter(e => e.kind === 'state' && e.new === 'on').length
      add(k === 'motion' ? 'Seen' : 'Opened', times ? `${times} ${times === 1 ? 'time' : 'times'}` : 'Not today')
      add(k === 'motion' ? 'Moving for' : 'Open for', on.length ? forLong(on) : null)
    }
    if (k === 'sensor') {
      const t = trace(events)
      if (t.pts.length > 1) { add('High', `${Math.round(t.high)}${sensorUnit(d, unit)}`); add('Low', `${Math.round(t.low)}${sensorUnit(d, unit)}`) }
    }
    if (k === 'camera') {
      const seen = events.filter(e => e.new === 'recording').length
      add('Seen today', seen ? `${seen} ${seen === 1 ? 'time' : 'times'}` : 'Nothing')
    }
  }
  add('Made by', d.maker)
  /* What the room as a whole is doing: the one piece of context a device cannot carry itself, and
     the reason a lamp went off when nobody touched it. */
  if (room && room.intent && room.intent !== 'occupied' && room.intent !== 'unknown') add('The room is on', LABELS[room.intent] ?? cap1(room.intent))
  return out.slice(0, 4)
}

/** How much of today a set of spans adds up to, said the way a person would. */
function forLong(on: { from: number; to: number }[], now = Date.now()): string {
  const day = now - new Date(now).setHours(0, 0, 0, 0)
  const mins = on.reduce((t, b) => t + (b.to - b.from), 0) * (day / 60000)
  return mins < 1 ? 'Under a minute' : mins < 60 ? `${Math.round(mins)} min` : `${Math.round(mins / 60)} h`
}

/* ---------- what it did today ----------
   Every row here is one line of the brain's event log, narrowed to this one device. A state change
   carries no author -- Home Assistant does not say who moved a lamp -- so nothing is claimed where
   nothing is known; an action the hub itself took does know, and says so. */
const BY: Record<string, string> = { user: 'by hand', timer: 'by its timer', assistant: 'by the assistant' }
const ACTION_WORDS: Record<string, string> = {
  on: 'Switched on', off: 'Switched off', lock: 'Locked', unlock: 'Unlocked', open: 'Opened', close: 'Shut',
  play: 'Played', pause: 'Paused', next: 'Skipped on', previous: 'Skipped back', volume: 'Volume changed',
  stop: 'Stopped', start: 'Sent out', return: 'Sent back', sound: 'Sound started', sound_off: 'Sound stopped',
  mode: 'Mode changed', preset: 'Preset changed',
}
function actionText(ev: Event, unit: string): string {
  const word = String(ev.new ?? '')
  let detail: any
  try { detail = ev.detail ? JSON.parse(ev.detail) : {} } catch { detail = {} }
  if (word.startsWith('fan ')) return `Fan for ${word.slice(4)}`
  if (word === 'fan off') return 'Fan off'
  if (word.startsWith('on for ')) return `On for ${word.slice(7)}`
  if (word === 'set') {
    if (detail.temperature != null) return `Asked for ${Math.round(detail.temperature)}${unit}`
    if (detail.position != null) return `Sent to ${detail.position}% open`
    if (detail.percentage != null) return `Set to ${detail.percentage}%`
    if (detail.brightness_pct != null) return `Dimmed to ${Math.round(detail.brightness_pct)}%`
  }
  if (word === 'on' && detail.brightness_pct != null) return `On at ${Math.round(detail.brightness_pct)}%`
  return ACTION_WORDS[word] ?? cap1(word)
}
function stateText(d: Device, to: string | null): string {
  const k = cap(d), s = String(to ?? '')
  if (k === 'motion') return s === 'on' ? 'Movement' : 'Went quiet'
  if (k === 'contact') return s === 'on' ? 'Opened' : 'Shut'
  if (k === 'sensor') return readingLabel({ ...d, state: s })
  if (k === 'lock') return s === 'locked' ? 'Locked' : s === 'unlocked' ? 'Unlocked' : cap1(s)
  if (k === 'cover') return s === 'open' ? 'Opened' : s === 'closed' ? 'Shut' : cap1(s)
  if (k === 'media') return s === 'playing' ? 'Started playing' : s === 'paused' ? 'Paused' : s === 'off' ? 'Off' : cap1(s)
  if (k === 'camera') return s === 'recording' ? 'Started recording' : s === 'streaming' ? 'Went live' : cap1(s)
  if (k === 'vacuum') return s === 'cleaning' ? 'Went out' : s === 'docked' ? 'Came back' : cap1(s)
  if (k === 'climate') return s === 'off' ? 'Switched off' : s === 'cool' ? 'Set to cool the room' : s === 'heat' ? 'Set to warm the room'
    : s === 'heat_cool' || s === 'auto' ? 'Set to either' : cap1(s)
  return s === 'on' ? 'On' : s === 'off' ? 'Off' : s === 'unavailable' ? 'Stopped answering' : cap1(s)
}
/** One log row as a line of the pane's foot, or null for the rows that say nothing to a person. */
export function moment(ev: Event, d: Device, now = Date.now(), unit = '°'): Moment | null {
  const u = (unit || '°').replace(/[^°CF]/g, '') || '°'
  if (ev.kind === 'action') {
    const by = BY[ev.source] ?? ''
    return { when: whenText(ev.ts, now), text: `${actionText(ev, u)}${by ? `, ${by}` : ''}` }
  }
  if (ev.kind === 'state') {
    if (!ev.new || ev.new === ev.old) return null
    return { when: whenText(ev.ts, now), text: stateText(d, ev.new) }
  }
  return null
}
/** The foot of the pane: the last few things this one device did, newest first. */
export function moments(events: Event[], d: Device, limit = 4, now = Date.now(), unit = '°'): Moment[] {
  const out: Moment[] = []
  for (const ev of events) {
    const m = moment(ev, d, now, unit)
    if (m) out.push(m)
    if (out.length >= limit) break
  }
  return out
}

/* ---------- why it is like that ----------
   One line under the reading. The first half is this device's own last move, the second is the
   room it is in -- which is how a lamp that went off on its own gets explained. */
export function whyLine(d: Device, events: Event[], room?: Room | null, now = Date.now(), unit = '°'): string {
  if (isDead(d)) return `${shortName(d, room)} has not answered since ${events.length ? whenText(events[0].ts, now) : 'some time ago'}.`
  const m = moments(events, d, 1, now, unit)[0]
  const mine = m ? `${m.text} ${m.when.startsWith('Yesterday, ') ? m.when.replace(/^Yesterday, /, 'yesterday at ') : `at ${m.when}`}.` : ''
  const held = room?.hold_until && room.hold_until * 1000 > now ? ' Routines are staying out of this room for now.' : ''
  return (mine + held).trim()
}

/* ---------- the day a watcher has had ----------
   A motion sensor, a door contact and a thermometer have no verb, so the only instrument they can
   be given is what they have seen. Both shapes below are built from the same state rows the foot
   of every other pane uses, laid across the day so far: midnight at the left, now at the right. */
const midnight = (now: number) => { const d = new Date(now); d.setHours(0, 0, 0, 0); return d.getTime() }

/** When a watcher was ON through the day, as fractions (0-1) of midnight-to-now. */
export function spans(events: Event[], now = Date.now(), from = midnight(now)): { from: number; to: number }[] {
  const width = Math.max(1, now - from)
  const rows = events.filter(e => e.kind === 'state' && e.ts * 1000 >= from).sort((a, b) => a.ts - b.ts)
  const out: { from: number; to: number }[] = []
  /* Whether it was already on at midnight is knowable from the first row's `old`, and only from
     there: the log keeps changes, not a reading every minute. */
  let open: number | null = rows.length && rows[0].old === 'on' ? 0 : null
  for (const e of rows) {
    const at = Math.min(1, Math.max(0, (e.ts * 1000 - from) / width))
    if (e.new === 'on' && open == null) open = at
    else if (e.new !== 'on' && open != null) { out.push({ from: open, to: Math.max(at, open + 0.004) }); open = null }
  }
  if (open != null) out.push({ from: open, to: 1 })
  return out
}

/** A numeric sensor's day: points across midnight-to-now, with the range they span. */
export function trace(events: Event[], now = Date.now(), from = midnight(now)): { pts: { x: number; y: number }[]; low: number; high: number } {
  const width = Math.max(1, now - from)
  const pts: { x: number; y: number }[] = []
  for (const e of events.filter(e => e.kind === 'state' && e.ts * 1000 >= from).sort((a, b) => a.ts - b.ts)) {
    const v = Number(e.new)
    if (Number.isFinite(v)) pts.push({ x: Math.min(1, Math.max(0, (e.ts * 1000 - from) / width)), y: v })
  }
  const ys = pts.map(p => p.y)
  return { pts, low: ys.length ? Math.min(...ys) : 0, high: ys.length ? Math.max(...ys) : 0 }
}
