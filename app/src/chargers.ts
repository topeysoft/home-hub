// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * A car charger (design/charger/, A with C's line): a card in its room that says Charging, Plugged in or
 * Ready, and while the car charges a line in Home's band. The brain makes the charger one device from the
 * unit's plug, charging and power readings (brain/hub/model.py, chargers()); nothing here is tapped,
 * because the car decides when it charges.
 */
import type { Device } from './api'
import { cap, done, isDead, roomOf, store } from './store'

export const isCharger = (d: Device) => cap(d) === 'charger'
export const isCharging = (d: Device) => d.state === 'charging'

export const kw = (p: unknown) => typeof p === 'number' ? `${p.toFixed(1)} kW` : ''

/** What its card says. */
export function chargerWords(d: Device): string {
  if (isDead(d)) return 'Not answering'
  if (isCharging(d)) return kw(d.attrs.power) ? `Charging · ${kw(d.attrs.power)}` : 'Charging'
  return d.state === 'plugged' ? 'Plugged in' : 'Ready'
}

export type ChargerLine = { id: string; title: string; sub: string; device: Device }

/** Home's band: every charger charging, and one that has just stopped, until the panel looks away. */
export function chargerBand(): ChargerLine[] {
  return store.rooms.flatMap(r => r.devices.filter(isCharger))
    .filter(d => isCharging(d) || done[`charger:${d.id}`])
    .map(d => {
      const room = roomOf(d)?.name ?? ''
      return isCharging(d)
        ? { id: d.id, device: d, title: 'The car is charging', sub: [kw(d.attrs.power), room].filter(Boolean).join(' · ') }
        : { id: d.id, device: d, title: 'The car stopped charging', sub: room }
    })
}
