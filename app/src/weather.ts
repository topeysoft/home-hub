/* What the forecast MEANS, which is where the words are.
 *
 * brain/hub/forecast.py is deliberately dumb: it turns HA's rows into numbers and stops, on the
 * grounds that a sentence belongs to the panel — which already owns the condition words, the clock
 * and the locale, the same way it works out sunrise from the location rather than asking the hub.
 * This is that half.
 *
 * The whole file exists to answer ONE question, and it is worth saying which: not "what will the
 * weather be", but "is there anything coming that changes what somebody does in the next few
 * hours". Those are different questions and only the second is worth a line on a wall. A panel that
 * says "Cloudy from 3 PM" has spent its most valuable line telling somebody about clouds.
 *
 * So a change here means wet weather starting or stopping, and nothing else is a change. When there
 * is none, these return nothing and the caller draws nothing — the line appears when the house has
 * something to say and is absent the rest of the time, which is the only honest way to spend a line
 * that is sometimes worth having.
 */
import { cap, isDead, shortName, store, WEATHER_LABEL } from './store'
import type { Day, Hour } from './api'

/* The conditions somebody would pick up an umbrella for. `exceptional` is not here on purpose: HA
   uses it for anything an integration cannot name, which is as often a gap in the data as a storm. */
export const WET = new Set(['rainy', 'pouring', 'hail', 'lightning', 'lightning-rainy', 'snowy', 'snowy-rainy'])

/* "4 PM", and "4:30 PM" only if an integration ever sends a row off the hour. Forecast rows are
   hours; printing ":00" on every one of them is four characters of nothing on the panel's best line. */
const time = (d: Date) => d.toLocaleTimeString([], d.getMinutes() ? { hour: 'numeric', minute: '2-digit' } : { hour: 'numeric' })
const parse = (at: string) => { const d = new Date(at); return Number.isNaN(d.getTime()) ? null : d }

export type Change = { kind: 'starts' | 'stops'; at: Date; condition: string }

/** The hours still ahead of `now`, in order — the rows the panel is allowed to draw. */
export function ahead(now: Date, hours?: Hour[]): Hour[] {
  const rows = hours ?? store.ambient.forecast?.hourly ?? []
  return rows.filter(h => { const d = parse(h.at); return d !== null && d.getTime() > now.getTime() - 30 * 60_000 })
}

/**
 * The next time wet weather starts or stops, or null.
 *
 * Measured against what it is doing NOW rather than against the first row: the current condition is
 * on the state and is fresher than any forecast row, and a house where it is already raining wants
 * to be told when it stops, not that it is raining.
 */
export function nextChange(now: Date, hours?: Hour[], nowCondition?: string): Change | null {
  const rows = ahead(now, hours)
  const wetNow = WET.has(nowCondition ?? store.ambient.weather?.condition ?? '')
  for (const h of rows) {
    const at = parse(h.at)
    if (!at) continue
    if (WET.has(h.condition) !== wetNow) return { kind: wetNow ? 'stops' : 'starts', at, condition: h.condition }
  }
  return null
}

/**
 * That change as a line, or '' when there is nothing coming.
 *
 * "Rain from 4 PM" rather than "Rain at 4 PM": at names a moment and from names a spell, and rain in
 * a forecast row is an hour of it. The stopping half says what it will be instead of what it will
 * stop being — "Clearing from 6 PM" is a promise, "Rain stops at 6 PM" is a negation and reads as
 * worse news than it is.
 */
export function changeLine(now: Date, hours?: Hour[], nowCondition?: string): string {
  const c = nextChange(now, hours, nowCondition)
  if (!c) return ''
  if (c.kind === 'stops') return `Clearing from ${time(c.at)}`
  return `${WEATHER_LABEL[c.condition] ?? 'Rain'} from ${time(c.at)}`
}

/** Today's high and low, where the house has a daily forecast for today. */
export function range(now: Date, days?: Day[]): { high: number | null; low: number | null } | null {
  const rows = days ?? store.ambient.forecast?.daily ?? []
  const today = rows.find(d => { const at = parse(d.at); return at !== null && at.toDateString() === now.toDateString() }) ?? null
  if (!today || (today.high == null && today.low == null)) return null
  return { high: today.high, low: today.low }
}

/** The days still ahead, today included. */
export function days(now: Date, rows?: Day[]): Day[] {
  const all = rows ?? store.ambient.forecast?.daily ?? []
  const midnight = new Date(now); midnight.setHours(0, 0, 0, 0)
  return all.filter(d => { const at = parse(d.at); return at !== null && at.getTime() >= midnight.getTime() })
}

/** Whether there is enough of a forecast to be worth opening a pane for. */
export const haveForecast = () => {
  const f = store.ambient.forecast
  return !!f && (f.hourly.length > 0 || f.daily.length > 0)
}

/**
 * What it is like INSIDE, against what it is like outside — the one number a weather app on a phone
 * can never show, because it is the only one that knows the house.
 *
 * The median rather than the mean, and that is the whole of the thinking here: a house has one
 * conservatory that bakes and one back bedroom nobody heats, and an average is dragged around by
 * both. The middle reading is the one somebody standing in the hall would agree with.
 *
 * Thermostats and temperature sensors together. A thermostat's reading is the better one — it is
 * sited for the room it holds — but a house with no thermostat at all still has a temperature, and
 * refusing to say it because the readings came from sensors would be pedantry.
 */
export function inside(): number | null {
  const reads: number[] = []
  /* Number(), not typeof === 'number': integrations are not consistent about types and a
     thermostat that reports "71" as a string is a thermostat whose reading is real. The hub's own
     forecast shaping has the same rule for the same reason. */
  const num = (v: unknown) => { const n = Number(v); return v !== null && v !== '' && Number.isFinite(n) ? n : null }
  for (const r of store.rooms) for (const d of r.devices) {
    if (isDead(d)) continue
    const c = cap(d) === 'climate' ? num(d.attrs?.current_temperature) : d.capability === 'sensor.temperature' ? num(d.state) : null
    if (c !== null) reads.push(c)
  }
  if (!reads.length) return null
  reads.sort((a, b) => a - b)
  return reads[(reads.length - 1) >> 1]
}

/**
 * What is open, by its own name, for the one sentence where the weather is the house's business.
 *
 * Names rather than kinds, because the panel cannot tell a window from a door: both arrive as the
 * `contact` capability and the device class that separated them does not survive into the semantic
 * model. Saying "the back door and the kitchen window" is what the house calls them anyway, and it
 * is right where a guess at "two windows" would have been wrong.
 */
export function openThings(): string[] {
  const out: string[] = []
  for (const r of store.rooms) for (const d of r.devices)
    if (cap(d) === 'contact' && d.state === 'on' && !isDead(d)) out.push(shortName(d, r).toLowerCase())
  return out
}

/** "the back door", "the back door and the kitchen window", "the back door, a window and 2 more". */
export function listed(names: string[]): string {
  if (names.length === 0) return ''
  if (names.length === 1) return `the ${names[0]}`
  if (names.length === 2) return `the ${names[0]} and the ${names[1]}`
  return `the ${names[0]}, the ${names[1]} and ${names.length - 2} more`
}
