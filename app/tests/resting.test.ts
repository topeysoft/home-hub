// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The resting wall's row of facts. The first test is the one that matters: the evening house has to
   read exactly as design/rest/LedgerB2.dc.html drew it, in that order, because a fact that moves
   around the wall is one nobody can find from across the room. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Room, Routine } from '../src/api'
import { store } from '../src/store'
import { clockParts, restingFacts, restWeather } from '../src/resting'
import { locale } from '../src/lang'

const dev = (id: string, name: string, capability: string, state: string, attrs: Record<string, any> = {}): Device =>
  ({ id, name, room_id: '', capability, state, attrs })
const room = (id: string, name: string, devices: Device[] = []): Room =>
  ({ id, name, devices: devices.map(d => ({ ...d, room_id: id })), intent: 'unknown', set_by: null, hold_until: null })

/* the house on the board, at 7:41 on a Monday evening */
const evening = (): Room[] => [
  room('living', 'Living room', [
    dev('l1', 'Ceiling light', 'light', 'on'),
    dev('l2', 'Floor lamp', 'light', 'on'),
    dev('t1', 'Thermostat', 'climate', 'heat', { current_temperature: 21.2, temperature: 21 }),
  ]),
  room('kitchen', 'Kitchen', [
    dev('k1', 'Kitchen lights', 'light', 'on'),
    dev('k2', 'Speaker', 'media', 'playing', { media_title: 'Evening Jazz' }),
  ]),
  room('front', 'Front door', [
    dev('f1', 'Front door', 'lock', 'locked'),
    dev('f2', 'Porch light', 'light', 'off'),
  ]),
]
const at = new Date(2026, 8, 28, 19, 41)
const porch: Routine = { id: 'r1', name: 'Porch light off', room: 'front', when: { time: '23:00' }, then: { intent: 'off' }, enabled: true } as Routine
const find = (key: string) => restingFacts(at).find(f => f.key === key)

beforeEach(() => {
  store.loaded = true
  store.rooms = evening()
  store.routines = []
  store.presence = null
  store.homeName = ''
  store.ambient = { location: { name: 'Chicago', lat: 41.88, lon: -87.63 }, weather: null }
})

describe('the row, as the board drew it', () => {
  it('reads Calm, 3 on, 21°, Playing, in that order', () => {
    expect(restingFacts(at).map(f => [f.value, f.where])).toEqual([
      ['Calm', 'Doors locked'],
      ['3 on', 'Living room, Kitchen'],
      ['21°', 'Living room'],
      ['Playing', 'Evening Jazz'],
    ])
  })

  it('draws only the lit lights in lamp color', () => {
    expect(restingFacts(at).filter(f => f.live).map(f => f.key)).toEqual(['lights'])
  })

  it('never shows more than four', () => {
    store.routines = [porch]
    expect(restingFacts(at)).toHaveLength(4)
  })
})

describe('the fourth place', () => {
  it('goes to the next routine once nothing is playing', () => {
    store.rooms[1].devices[1].state = 'paused'
    store.routines = [porch]
    expect(find('playing')).toBeUndefined()
    expect(find('next')?.where).toBe('Porch light off')
    const t = clockParts(new Date(2026, 8, 28, 23, 0))
    expect(find('next')).toMatchObject({ value: t.time, period: t.period })
  })

  it('is left out when nothing plays and nothing is due', () => {
    store.rooms[1].devices[1].state = 'idle'
    expect(restingFacts(at).map(f => f.key)).toEqual(['house', 'lights', 'inside'])
  })
})

describe('the house fact', () => {
  it('says which door is open, in lamp color', () => {
    store.rooms[2].devices[0].state = 'unlocked'
    expect(find('house')).toMatchObject({ value: 'Unlocked', where: 'Front door', live: true })
  })

  it('says Away when nobody is home', () => {
    store.presence = { somebody: false } as typeof store.presence
    expect(find('house')?.value).toBe('Away')
  })
})

describe('what the house cannot give is left out, not blank', () => {
  it('has no inside fact without a thermometer', () => {
    store.rooms[0].devices.pop()
    expect(find('inside')).toBeUndefined()
  })

  it('says Off when every light is off', () => {
    for (const r of store.rooms) for (const d of r.devices) if (d.capability === 'light') d.state = 'off'
    expect(find('lights')).toMatchObject({ value: 'Off', live: false })
  })

  it('shows nothing until the house has been read', () => {
    store.loaded = false
    expect(restingFacts(at)).toEqual([])
  })
})

describe('the weather in the corner', () => {
  it('is left out when the house has no weather', () => {
    expect(restWeather()).toBeNull()
  })

  it('gives the temperature and the condition in words', () => {
    store.ambient = { ...store.ambient, weather: { temperature: 78.4, unit: '°F', condition: 'partlycloudy' } } as typeof store.ambient
    expect(restWeather()).toEqual({ temp: '78°', label: 'Partly cloudy' })
  })
})

describe('the clock', () => {
  it('keeps its AM or PM, apart from the digits so it can be set small', () => {
    const { time, period } = clockParts(at)
    const whole = at.toLocaleTimeString(locale(), { hour: 'numeric', minute: '2-digit' })
    expect(time + period).toBe(whole.replace(/\s/g, ''))
    expect(time).not.toContain(period || '#')
  })
})
