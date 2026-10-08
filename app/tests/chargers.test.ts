// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A car charger (design/charger/, A with C's line): its card's words, and Home's band while it charges --
   including the rule that a line nobody has looked away from yet does not vanish when the car stops. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { chargerBand, chargerWords } from '../src/chargers'
import { activity, done, forgetDone, noteCharger, restingLine, roomActive, store, whatsOn } from '../src/store'

const charger = (state: string, power: number | null = null): Device =>
  ({ id: 'binary_sensor.twc', name: 'Car charger', room_id: 'garage', capability: 'charger', kind: 'charger', state, attrs: { power } })
const garage = (d: Device): Room => ({ id: 'garage', name: 'Garage', devices: [d], intent: 'unknown', set_by: null, hold_until: null })

describe('a car charger', () => {
  beforeEach(() => forgetDone(true))

  it('says what it is doing in three words, and nothing to tap', () => {
    expect(chargerWords(charger('charging', 7.2))).toBe('Charging · 7.2 kW')
    expect(chargerWords(charger('charging'))).toBe('Charging')
    expect(chargerWords(charger('plugged'))).toBe('Plugged in')
    expect(chargerWords(charger('ready'))).toBe('Ready')
    expect(chargerWords(charger('unavailable'))).toBe('Not answering')
  })

  it('charging is the room doing something; plugged in is the room resting', () => {
    expect(activity(garage(charger('charging', 7.2)))).toBe('Charging the car')
    expect(roomActive(garage(charger('charging', 7.2)))).toBe(true)
    expect(roomActive(garage(charger('plugged')))).toBe(false)
    expect(restingLine(garage(charger('plugged')))).toBe('Car plugged in')
  })

  it('is never in "on right now": it is said in the band instead', () => {
    store.rooms = [garage(charger('charging', 7.2))]
    expect(whatsOn()).toEqual([])
  })

  it('is a line in Home\'s band while it charges, with the power and the room', () => {
    store.rooms = [garage(charger('charging', 7.2))]
    expect(chargerBand().map(l => [l.title, l.sub])).toEqual([['The car is charging', '7.2 kW · Garage']])
    store.rooms = [garage(charger('plugged'))]
    expect(chargerBand()).toEqual([])
  })

  it('keeps its line when the car stops, until the panel looks away', () => {
    const was = charger('charging', 7.2), now = charger('plugged')
    noteCharger(was, now)
    store.rooms = [garage(now)]
    expect(chargerBand().map(l => l.title)).toEqual(['The car stopped charging'])
    forgetDone(true)
    expect(chargerBand()).toEqual([])
  })

  it('charging again takes back the kept line', () => {
    noteCharger(charger('charging'), charger('plugged'))
    noteCharger(charger('plugged'), charger('charging', 11))
    expect(done['charger:binary_sensor.twc']).toBeUndefined()
  })
})
