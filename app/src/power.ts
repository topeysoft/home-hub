// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The house's own power, in words (design/energy/, B with C's sun; the brain's half is brain/hub/power.py).
 *
 * Nothing about power is on the wall until it changes what somebody would do. Then it is one line in the
 * band: the power is out and the battery has the house, the battery getting low while it still is, the
 * power back, and sun to spare -- the battery full and the roof still sending power away, which is the
 * moment for the dryer or the car. Each line opens the power pane. The only other trace is the sun in the
 * weather drawing, which warms with what the roof is making.
 */
import type { Power, PowerDay } from './api'
import { kw } from './chargers'

export type PowerLine = { id: 'out' | 'low' | 'back' | 'spare'; title: string; sub: string; needs: boolean }

/* Below this, with the power out, the line stops being news and starts being a warning. */
export const LOW = 20

const pct = (v: number) => `${Math.round(v)}%`

/** A stretch of hours, the way somebody would say it: "about 14 hours", "about 40 minutes". */
export function aboutHours(h: number): string {
  if (h >= 24) return 'more than a day'
  if (h >= 1.5) return `about ${Math.round(h)} hours`
  if (h >= 0.75) return 'about an hour'
  return `about ${Math.max(5, Math.round(h * 12) * 5)} minutes`
}

/** How long the battery would carry the house at what it is using now; '' where that cannot be known. */
export function lasts(p: Power): string {
  if (p.left == null || p.house == null) return ''
  return aboutHours(p.left / Math.max(p.house, 0.2))
}

/** How long something lasted, exactly enough to be told: "2 hours 10 minutes". */
export function lasted(seconds: number): string {
  const m = Math.round(seconds / 60), h = Math.floor(m / 60), mm = m % 60
  if (!m) return 'less than a minute'
  return [h ? `${h} hour${h === 1 ? '' : 's'}` : '', mm ? `${mm} minute${mm === 1 ? '' : 's'}` : ''].filter(Boolean).join(' ')
}

/** Home's band: what the house's power has to say right now, most urgent first. Empty most of the time. */
export function powerBand(p: Power | null): PowerLine[] {
  if (!p) return []
  if (p.grid_up === false) {
    if (p.has_battery && p.charge != null && p.charge <= LOW)
      return [{ id: 'low', title: 'The battery is getting low', sub: `${pct(p.charge)} left, and the power is still out`, needs: true }]
    if (!p.has_battery) return [{ id: 'out', title: 'The power is out', sub: 'The grid is down', needs: true }]
    const how = lasts(p)
    return [{ id: 'out', title: 'The power is out — the battery has the house', needs: true,
              sub: p.charge != null ? `${pct(p.charge)}${how ? `, ${how} as things are` : ''}` : 'The grid is down' }]
  }
  const lines: PowerLine[] = []
  if (p.back) lines.push({ id: 'back', title: 'The power is back', sub: `It was out for ${lasted(p.back.lasted)}`, needs: false })
  if (p.spare) lines.push({ id: 'spare', title: 'Sun to spare', needs: false,
    sub: p.has_battery ? 'The battery is full: a good time for the dryer or the car' : 'A good time for the dryer or the car' })
  return lines
}

/** How warm the sun in the weather drawing is, 0 to 1: what the roof is making against the most it has
    made this month. A roof making nothing leaves the drawing exactly as the weather alone would. */
export function warmth(solar: number | null | undefined, peak: number | null | undefined): number {
  if (solar == null || solar < 0.05) return 0
  return Math.min(1, solar / Math.max(peak ?? 0, solar, 1))
}

const some = (v: number | null | undefined, over = 0.05) => v != null && v > over

/** The pane's sentence: what the power is doing, in one or two plain sentences. */
export function powerSentence(p: Power): string {
  if (p.grid_up === false) {
    const how = lasts(p)
    return p.has_battery ? `The power is out. The battery has the house${how ? `, and should last ${how} as things are` : ''}.` : 'The power is out.'
  }
  const toGrid = some(p.grid == null ? null : -p.grid, 0.1), charging = some(p.battery, 0.1), giving = some(p.battery == null ? null : -p.battery, 0.1)
  const full = fullIn(p)
  if (some(p.solar) && p.house != null && p.solar! > p.house + 0.1) {
    if (charging) return `The sun is making more than the house needs. The battery is charging${full ? ` and should be full in ${full}` : ''}${toGrid ? '; the rest is going to the grid' : ''}.`
    return toGrid ? 'The sun is making more than the house needs, and the rest is going to the grid.' : 'The sun is making more than the house needs.'
  }
  if (some(p.solar)) return `The sun is making some of what the house needs, and ${giving ? 'the battery' : 'the grid'} is making up the rest.`
  if (giving) return `The battery has the house${p.charge != null ? `, at ${pct(p.charge)}` : ''}.`
  if (some(p.grid, 0.1)) return 'The house is running on the grid.'
  return ''
}

/** How long until the battery is full at the rate it is charging, from how much it holds now. */
export function fullIn(p: Power): string {
  if (!some(p.battery, 0.1) || p.charge == null || p.charge >= 99 || !p.left || p.charge <= 0) return ''
  const capacity = p.left / (p.charge / 100)
  return aboutHours(capacity * (1 - p.charge / 100) / p.battery!)
}

/** The four circles' small lines in the pane's picture. */
export function flowWords(p: Power) {
  const battery = p.charge == null ? '' : `${pct(p.charge)}, ${some(p.battery) ? 'charging' : some(p.battery == null ? null : -p.battery) ? 'powering the house' : p.charge >= 99 ? 'full' : 'resting'}`
  const grid = p.grid_up === false ? 'Out' : some(p.grid == null ? null : -p.grid) ? `sending ${kw(-p.grid!)}` : some(p.grid) ? `supplying ${kw(p.grid!)}` : 'Not in use'
  return { sun: some(p.solar) ? kw(p.solar) : 'Nothing now', house: p.house != null ? `using ${kw(p.house)}` : '', battery, grid }
}

/** Where the power from the sun is going, as the three kW figures on the picture's lines. */
export function flows(p: Power) {
  return {
    toHouse: some(p.solar) && p.house != null ? Math.min(p.solar!, p.house) : 0,
    toBattery: some(p.solar) && some(p.battery) ? p.battery! : 0,
    toGrid: some(p.solar) && some(p.grid == null ? null : -p.grid) ? -p.grid! : 0,
  }
}

/** The day so far as two paths, the sun's area and the house's line, in a box of the given size. The
    axis runs from 6 AM to 9 PM; the hours outside it are night for the roof and do not need the room. */
export function dayPaths(day: PowerDay | null, w: number, h: number) {
  if (!day?.curve.length) return { sun: '', house: '', now: null as number | null, max: 0 }
  const start = day.since + 6 * 3600, span = 15 * 3600
  const x = (t: number) => Math.max(0, Math.min(w, (t - start) / span * w))
  const max = Math.max(1, ...day.curve.map(c => Math.max(c.solar ?? 0, c.house ?? 0))) * 1.1
  const y = (v: number) => h - v / max * h
  const sunPts = day.curve.filter(c => c.solar != null).map(c => `${x(c.at).toFixed(1)},${y(c.solar!).toFixed(1)}`)
  const housePts = day.curve.filter(c => c.house != null).map(c => `${x(c.at).toFixed(1)},${y(c.house!).toFixed(1)}`)
  const first = day.curve.find(c => c.solar != null), last = [...day.curve].reverse().find(c => c.solar != null)
  const sun = sunPts.length && first && last ? `M${x(first.at).toFixed(1)},${h} L${sunPts.join(' L')} L${x(last.at).toFixed(1)},${h} Z` : ''
  return { sun, house: housePts.length ? `M${housePts.join(' L')}` : '', now: last ? x(last.at) : null, max }
}
