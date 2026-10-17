// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A screen on the wall that is not the hub (design/companion/, C).

   The wall unit and the tablet open the panel with ?screen=1. That is remembered, so a reload or a
   restart without it is still a screen. A screen joins the house the way a phone does, then says
   which room it hangs in: it opens on that room and wakes to it. The room is kept here as well as on
   the hub, because a house with no passcode has no phone records to keep it on. */
import { ref } from 'vue'
import type { Phone, Room } from './api'
import { kindFor } from './art'

const SCREEN = 'screen', ROOM = 'screen-room'

function get(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function put(k: string, v: string | null) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch {} }

export function isScreen(search = location.search): boolean {
  if (new URLSearchParams(search).get('screen') === '1') { put(SCREEN, '1'); return true }
  return get(SCREEN) === '1'
}

const room = ref(get(ROOM))   // a ref, so the panel notices when the room is changed from How it looks
export const screenRoom = () => room.value
export function keepScreenRoom(id: string | null) { room.value = id; put(ROOM, id) }

/** The room a screen opens on and wakes to, if it has one the house still has. */
export function homeRoom(rooms: Room[], screen = isScreen(), id = screenRoom()): string | null {
  return screen && id && rooms.some(r => r.id === id) ? id : null
}

/** Ask which room this screen is in: a screen, in the house, with no room yet (or one since taken away). */
export function needsRoom(rooms: Room[], screen = isScreen(), id = screenRoom()): boolean {
  return screen && rooms.length > 0 && !homeRoom(rooms, screen, id)
}

const WORD: Record<string, string> = { lock: 'door', tv: 'TV', speaker: 'speaker', thermostat: 'heating', camera: 'camera',
  doorbell: 'doorbell', blind: 'blinds', fan: 'fan', plug: 'plug', vacuum: 'vacuum', charger: 'charger' }

/** What is in a room, in the few words under its name: "4 lights · door". */
export function roomLine(room: Room, screens: Phone[] = []): string {
  const others = screens.filter(p => p.room === room.id && !p.me)
  if (others.length) return others.length === 1 ? 'a screen already' : `${others.length} screens already`
  const lights = room.devices.filter(d => d.capability === 'light').length
  const words: string[] = []
  for (const d of room.devices) {
    if (d.capability === 'light') continue
    const k = kindFor(d.capability, d.name), w = k && WORD[k]
    if (w && !words.includes(w)) words.push(w)
  }
  const parts = [lights ? `${lights} light${lights === 1 ? '' : 's'}` : '', ...words.slice(0, lights ? 1 : 2)].filter(Boolean)
  return parts.length ? parts.join(' · ') : 'nothing in it yet'
}

/** The button under the rooms: "Open on the hallway", or "Open on Jordan's room" for a name that is somebody's. */
export function openOn(name: string): string {
  return /['’]/.test(name) ? `Open on ${name}` : `Open on the ${name.toLowerCase()}`
}
