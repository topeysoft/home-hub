// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What the resting wall says about the house, in words big enough to read from across the room.
 * Drawn first as design/rest/LedgerB2.dc.html, and revised as design/rest/CornerF.dc.html.
 *
 * The resting screen used to be the clock over one sentence ("Something is on in 2 rooms"), which
 * said that something was on but not what or where, and never mentioned the warmth inside or the
 * music still playing in the kitchen. Anybody walking past had to wake the panel to learn anything.
 * Now it is a row of up to four facts, each one or two words set large (Calm, 3 on, 21°, Playing)
 * with where it is written small underneath. The order is fixed so a fact is always in the same
 * place on the wall, and a fact the house cannot give is left out rather than shown blank.
 *
 * The fourth place is shared. Music takes it while something is playing, and otherwise the next
 * routine does. The board argued that four facts at this size fill the width, so a fifth has to
 * replace one rather than join them.
 *
 * The weather is not one of the facts. It is the house's own drawing in the top right corner
 * (CornerF), set as large as the facts so it reads from as far away. A long routine name wraps to two
 * lines under its time rather than pushing the row off the edges of the wall.
 */
import type { Device } from './api'
import { cap, isDead, roomOf, store, weatherParts } from './store'
import { temperature } from './rooms'
import { upcoming } from './upcoming'
import { locale } from './lang'

export type Fact = {
  key: 'house' | 'lights' | 'inside' | 'playing' | 'next'
  icon: string
  value: string    // the big words, read from across the room
  where: string    // the small line under them
  period?: string  // AM or PM after a time, set small beside it
  live: boolean    // drawn in lamp color: a light is on, or a door is open
}

const all = () => store.rooms.flatMap(r => r.devices)
const names = (ds: Device[]) => {
  const rooms = [...new Set(ds.map(d => roomOf(d)?.name).filter(Boolean))] as string[]
  return rooms.length <= 2 ? rooms.join(', ') : `in ${rooms.length} rooms`
}

/** The house as a whole: an open door first, then nobody home, then calm. */
function house(): Fact {
  const locks = all().filter(d => cap(d) === 'lock' && !isDead(d))
  const open = locks.filter(d => d.state === 'unlocked' || d.state === 'open')
  if (open.length) return { key: 'house', icon: 'lock', value: 'Unlocked', where: open.length === 1 ? open[0].name : `${open.length} doors`, live: true }
  if (store.presence?.somebody === false) return { key: 'house', icon: 'home', value: 'Away', where: "Nobody's home", live: false }
  return { key: 'house', icon: 'home', value: 'Calm', where: locks.length ? 'Doors locked' : store.homeName || 'The house', live: false }
}

function lights(): Fact | null {
  const ls = all().filter(d => cap(d) === 'light' && !isDead(d))
  if (!ls.length) return null
  const on = ls.filter(d => d.state === 'on')
  return on.length
    ? { key: 'lights', icon: 'light', value: `${on.length} on`, where: names(on), live: true }
    : { key: 'lights', icon: 'light', value: 'Off', where: 'Every light', live: false }
}

/** A thermostat's own reading first, since that is the number people set the house by; then any room that reads one. */
function inside(): Fact | null {
  const t = all().find(d => cap(d) === 'climate' && !isDead(d) && Number.isFinite(Number(d.attrs.current_temperature)))
  if (t) return { key: 'inside', icon: 'thermometer', value: `${Math.round(Number(t.attrs.current_temperature))}°`, where: roomOf(t)?.name ?? t.name, live: false }
  for (const r of store.rooms) {
    const v = temperature(r)
    if (v) return { key: 'inside', icon: 'thermometer', value: v, where: r.name, live: false }
  }
  return null
}

function fourth(now: Date): Fact | null {
  const m = all().find(d => cap(d) === 'media' && d.state === 'playing')
  if (m) return { key: 'playing', icon: 'music', value: 'Playing', where: m.attrs.media_title || roomOf(m)?.name || m.name, live: false }
  const u = upcoming(now)
  if (u) { const t = clockParts(u.at); return { key: 'next', icon: 'clock', value: t.time, period: t.period, where: u.routine.name, live: false } }
  return null
}

/** The facts in the order the wall shows them, or none until the house has been read. */
export function restingFacts(now = new Date()): Fact[] {
  if (!store.loaded) return []
  return [house(), lights(), inside(), fourth(now)].filter((f): f is Fact => !!f)
}

/** The temperature and the condition in words, for the corner beside the drawing; null when the house has no weather. */
export function restWeather(): { temp: string; label: string } | null {
  const w = weatherParts()
  return w.temp || w.label ? w : null
}

/** The time and its AM or PM apart, so the period can be set small beside the digits: from across the
    room the digits are what is read, and the sky already says which half of the day it is. A house on
    a 24-hour clock has no period, and gets an empty one. */
export function clockParts(d: Date): { time: string; period: string } {
  const parts = new Intl.DateTimeFormat(locale(), { hour: 'numeric', minute: '2-digit' }).formatToParts(d)
  return {
    time: parts.filter(p => p.type !== 'dayPeriod').map(p => p.value).join('').trim(),
    period: parts.find(p => p.type === 'dayPeriod')?.value ?? '',
  }
}
