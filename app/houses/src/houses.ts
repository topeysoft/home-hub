// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The houses this phone has joined, and how to reach each one (design/houses/, decided 2 and 3 October).
 *
 * The list is the phone's: in this app's own storage, never on a server -- there is no account, on purpose.
 * Each house is tried on its Wi-Fi first, by the name the house gave for home, and over the internet after,
 * by its own name: the same order the printer app keeps for printers, and the panel keeps for itself.
 *
 * The rules a screen leans on are plain functions here, so tests/houses.test.ts can pin them to the boards.
 */
import { reactive } from 'vue'
import { all, put } from './db'

export type HouseRecord = {
  id: string          // the house's label in the zone: `temi` of temi.elyir.app
  name: string        // what this phone calls it (AppName): only this phone sees it
  origin: string      // https://temi.elyir.app
  lan: string         // the house's name at home, as it last said: 192-168-86-53.temi.home.elyir.app
  token: string       // this phone's pass for this house
  added: number
  opened: number      // when it was last opened here: where the app opens when no house answers at home
}

/** Where a house was found: on its own Wi-Fi, over the internet, there but not letting this phone in from out there, or not at all. */
export type Reach = 'checking' | 'here' | 'away' | 'home-only' | 'offline'

export type Glance = { temp: string; notes: number; first: string }

export type House = HouseRecord & { reach: Reach; glance: Glance | null }

export const state = reactive({ houses: [] as House[], loaded: false })

// ---- the pure parts ----------------------------------------------------------------------------

/** The code as a person typed it: case, spaces and dashes are how it was read, not part of it. */
export const codeOf = (typed: string) => (typed || '').toUpperCase().replace(/[^A-Z0-9]/g, '')

/** What the move carries in the fragment: /add#h=<house>&c=<code>. */
export function addLink(hash: string): { house: string; code: string } | null {
  const q = new URLSearchParams((hash || '').replace(/^#/, ''))
  const house = (q.get('h') || '').toLowerCase(), code = codeOf(q.get('c') || '')
  return /^[a-z0-9-]{1,30}$/.test(house) && code.length === 8 ? { house, code } : null
}

/** A house's own origin, from its label and this app's zone; on a developer's machine, the mock brain. */
export function originOf(label: string, here: { hostname: string; protocol: string }, dev = 'http://localhost:8399'): string {
  if (here.hostname === 'localhost' || here.hostname === '127.0.0.1') return dev
  return `https://${label}.${here.hostname.split('.').slice(1).join('.')}`
}

/** The house a house's address names: `temi` of https://temi.elyir.app or temi.elyir.app. */
export function labelOf(address: string): string {
  const host = address.replace(/^https?:\/\//, '').split('/')[0].toLowerCase()
  return host.split('.')[0].replace(/[^a-z0-9-]/g, '')
}

/** B, where you are: the house whose Wi-Fi this phone is on; else the one opened last. */
export function houseToOpen(houses: Pick<House, 'id' | 'reach' | 'opened'>[]): string | null {
  const here = houses.find(h => h.reach === 'here')
  if (here) return here.id
  return [...houses].sort((a, b) => b.opened - a.opened)[0]?.id ?? null
}

/** On an iPhone in Safari, nothing is added: the Home Screen app keeps its own storage (AppSafari). */
export const iphoneSafari = (ua: string, standalone: boolean) => /iPhone|iPad|iPod/.test(ua) && !standalone

export const standalone = () =>
  matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true

// ---- talking to a house ------------------------------------------------------------------------

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` })

/** The pass a move hands over, for the code the house showed. */
export async function claim(origin: string, code: string): Promise<{ token: string; lan: string | null; home: string }> {
  const r = await fetch(`${origin}/phones/move/claim`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: codeOf(code) }) })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.detail || 'The house did not answer. Try again in a moment.')
  let home = 'Home'
  try { home = (await (await fetch(`${origin}/phones/me`, { headers: bearer(body.token) })).json()).home || home } catch { /* the name is only a suggestion */ }
  return { token: body.token, lan: body.lan ?? null, home }
}

/** Which named houses are on the same Wi-Fi as this phone (AppFirst). The relay (nearby.elyir.app) knows only
    which names log in from this phone's address, and a printer has a name there too, so each name is asked
    whether it is a house: a hub answers /alive with its build, to this app, and a printer answers with its page
    or not at all. Found 3 October, when the list on the maker's own Wi-Fi was one house and three printers.
    A hub too old to answer this app is left out as well -- it could not be added from here anyway. */
export async function nearby(here: { hostname: string }): Promise<string[]> {
  if (here.hostname === 'localhost') return []
  const zone = here.hostname.split('.').slice(1).join('.')
  let names: string[]
  try {
    const r = await fetch(`https://nearby.${zone}/nearby`, { cache: 'no-store', signal: AbortSignal.timeout(4000) })
    names = ((await r.json()).names ?? []).filter((n: unknown) => typeof n === 'string')
  } catch { return [] }
  const houses = await Promise.all(names.map(n => isHouse(`https://${n}.${zone}`)))
  return names.filter((_, i) => houses[i])
}

/** Whether the name answers like a hub: /alive, from this app, as JSON with the build in it. */
export async function isHouse(origin: string): Promise<boolean> {
  try {
    const r = await fetch(`${origin}/alive`, { cache: 'no-store', signal: AbortSignal.timeout(4000) })
    if (!r.ok || !(r.headers.get('content-type') || '').includes('application/json')) return false
    const body = await r.json()
    return body?.ok === true && typeof body.version === 'string'
  } catch { return false }
}

/** Where a house can be reached from here, and how it answers: its Wi-Fi name for a second and a half, then its own name. */
export async function reach(h: House): Promise<{ reach: Reach; base: string }> {
  if (h.lan) {
    try {
      const r = await fetch(`https://${h.lan}/alive`, { signal: AbortSignal.timeout(1500), cache: 'no-store' })
      if (r.ok) return { reach: 'here', base: `https://${h.lan}` }
    } catch { /* not on that Wi-Fi, or the router keeps private answers back */ }
  }
  try {
    const r = await fetch(`${h.origin}/phones/me`, { headers: bearer(h.token), signal: AbortSignal.timeout(8000), cache: 'no-store' })
    if (r.status === 403) return { reach: 'home-only', base: h.origin }
    if (r.ok) {
      const me = await r.json()
      if (me.lan && me.lan !== h.lan) { h.lan = me.lan; await save(h) }
      return { reach: 'away', base: h.origin }
    }
  } catch { /* nobody answered */ }
  return { reach: 'offline', base: h.origin }
}

/** One line of how a house is, for Houses (HereB-sheet): its weather, and anything that needs somebody. */
export async function glance(h: House, base: string): Promise<Glance | null> {
  try {
    const [amb, health] = await Promise.all([
      fetch(`${base}/ambient`, { headers: bearer(h.token), signal: AbortSignal.timeout(6000) }).then(r => r.ok ? r.json() : null),
      fetch(`${base}/health`, { headers: bearer(h.token), signal: AbortSignal.timeout(6000) }).then(r => r.ok ? r.json() : null),
    ])
    const t = amb?.weather?.temperature
    const notes = health?.notes ?? []
    return { temp: typeof t === 'number' ? `${Math.round(t)}°` : '', notes: notes.length, first: notes[0]?.band || notes[0]?.text || '' }
  } catch { return null }
}

// ---- the list ----------------------------------------------------------------------------------

function record(h: HouseRecord): HouseRecord {
  const { id, name, origin, lan, token, added, opened } = h
  return { id, name, origin, lan, token, added, opened }
}

export async function save(h: HouseRecord) { await put(record(h)) }

export async function load() {
  const got = await all<HouseRecord>()
  state.houses = got.map(h => ({ ...h, reach: 'checking' as Reach, glance: null }))
  state.loaded = true
}

export async function add(h: HouseRecord) {
  await save(h)
  const i = state.houses.findIndex(x => x.id === h.id)
  const live: House = { ...h, reach: 'checking', glance: null }
  if (i >= 0) state.houses[i] = live
  else state.houses.push(live)
}
