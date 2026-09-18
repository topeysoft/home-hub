// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What the forecast means, which is the half the hub deliberately does not do.
 *
 * The rule under nearly every case here: a change is wet weather starting or stopping, and nothing
 * else is a change. "Cloudy from 3 PM" is not news and must never take the line. */
import { beforeEach, describe, expect, it } from 'vitest'
import { store } from '../src/store'
import { ahead, changeLine, days, haveForecast, inside, nextChange, range } from '../src/weather'
import type { Day, Hour } from '../src/api'

const NOW = new Date('2026-09-15T12:00:00')
const hour = (h: number, condition: string, temperature = 78): Hour =>
  ({ at: new Date(2026, 8, 15, h).toISOString(), condition, temperature, rain: null })
const day = (d: number, condition: string, high: number | null, low: number | null): Day =>
  ({ at: new Date(2026, 8, d).toISOString(), condition, high, low, rain: null })

beforeEach(() => { store.ambient = { location: null, weather: null, forecast: null } as any })

describe('the next change', () => {
  it('finds rain coming and says when it starts', () => {
    const rows = [hour(13, 'partlycloudy'), hour(14, 'cloudy'), hour(16, 'rainy'), hour(17, 'rainy')]
    expect(nextChange(NOW, rows, 'partlycloudy')?.at.getHours()).toBe(16)
    expect(changeLine(NOW, rows, 'partlycloudy')).toMatch(/^Rain from 4(:00)? PM$/)
  })

  it('says nothing at all when nothing is coming', () => {
    /* The point of the whole module. A line that is always there is furniture; this one earns its
       place by being absent most of the time. */
    const rows = [hour(13, 'sunny'), hour(14, 'partlycloudy'), hour(15, 'cloudy')]
    expect(nextChange(NOW, rows, 'sunny')).toBeNull()
    expect(changeLine(NOW, rows, 'sunny')).toBe('')
  })

  it('measures against what it is doing now, not against the first row', () => {
    /* The current condition is on the state and is fresher than any forecast row. A house where it
       is already raining wants to know when it STOPS. */
    const rows = [hour(13, 'rainy'), hour(14, 'rainy'), hour(15, 'cloudy')]
    const c = nextChange(NOW, rows, 'rainy')
    expect(c?.kind).toBe('stops')
    expect(c?.at.getHours()).toBe(15)
    expect(changeLine(NOW, rows, 'rainy')).toMatch(/^Clearing from 3(:00)? PM$/)
  })

  it('names the wet weather it found rather than always saying rain', () => {
    expect(changeLine(NOW, [hour(15, 'snowy')], 'cloudy')).toMatch(/^Snow from/)
    expect(changeLine(NOW, [hour(15, 'lightning-rainy')], 'cloudy')).toMatch(/^Thunderstorm from/)
  })

  it('does not treat an unnameable condition as weather', () => {
    /* HA's `exceptional` is as often a gap in an integration's data as it is a storm, and "Unusual
       weather from 3 PM" on a clear afternoon is the panel inventing an emergency. */
    expect(nextChange(NOW, [hour(15, 'exceptional')], 'sunny')).toBeNull()
  })

  it('ignores hours that have already been', () => {
    const rows = [hour(9, 'rainy'), hour(13, 'sunny'), hour(15, 'sunny')]
    expect(nextChange(NOW, rows, 'sunny')).toBeNull()
    expect(ahead(NOW, rows).length).toBe(2)
  })

  it('survives a row whose time will not parse', () => {
    const rows = [{ at: 'whenever', condition: 'rainy', temperature: 70, rain: null }, hour(16, 'rainy')]
    expect(nextChange(NOW, rows as Hour[], 'sunny')?.at.getHours()).toBe(16)
  })
})

describe('the day', () => {
  it('takes the high and low off today, not off the first row it sees', () => {
    const rows = [day(14, 'sunny', 90, 70), day(15, 'rainy', 84, 61), day(16, 'sunny', 88, 64)]
    expect(range(NOW, rows)).toEqual({ high: 84, low: 61 })
  })

  it('has no range when today is not in the forecast', () => {
    expect(range(NOW, [day(16, 'sunny', 88, 64)])).toBeNull()
  })

  it('keeps a day that has a high and no low', () => {
    /* Plenty of integrations send one and not the other, and a high on its own is most of what a
       row says. */
    expect(range(NOW, [day(15, 'sunny', 84, null)])).toEqual({ high: 84, low: null })
    expect(range(NOW, [day(15, 'sunny', null, null)])).toBeNull()
  })

  it('drops the days that have already gone', () => {
    const rows = [day(13, 'sunny', 80, 60), day(15, 'rainy', 84, 61), day(16, 'sunny', 88, 64)]
    expect(days(NOW, rows).length).toBe(2)
  })
})

describe('whether there is one at all', () => {
  it('is false for no forecast and for an empty one', () => {
    expect(haveForecast()).toBe(false)
    store.ambient.forecast = { hourly: [], daily: [] }
    expect(haveForecast()).toBe(false)
  })

  it('is true on half a forecast, because half is what many houses get', () => {
    store.ambient.forecast = { hourly: [], daily: [day(15, 'sunny', 84, 61)] }
    expect(haveForecast()).toBe(true)
  })
})

describe('what it is like in here', () => {
  const dev = (id: string, capability: string, state: string, attrs: any = {}) => ({ id, name: id, room_id: 'r', capability, state, attrs })
  const house = (...devices: any[]) => { store.rooms = [{ id: 'r', name: 'Room', devices, intent: 'occupied' }] as any }

  it('is the middle reading, not the average', () => {
    /* A house has one conservatory that bakes and one back bedroom nobody heats, and a mean is
       dragged around by both. The middle is the number somebody in the hall would agree with. */
    house(dev('a', 'sensor.temperature', '64'), dev('b', 'sensor.temperature', '71'), dev('c', 'sensor.temperature', '96'))
    expect(inside()).toBe(71)
  })

  it('reads a thermostat and a sensor alike', () => {
    house(dev('t', 'climate', 'cool', { current_temperature: 70 }), dev('s', 'sensor.temperature', '74'))
    expect(inside()).toBe(70)
  })

  it('takes a reading an integration sent as a string', () => {
    house(dev('t', 'climate', 'cool', { current_temperature: '71.4' }))
    expect(inside()).toBe(71.4)
  })

  it('has nothing to say when the house measures nothing', () => {
    house(dev('l', 'light', 'on'))
    expect(inside()).toBeNull()
    house()
    expect(inside()).toBeNull()
  })

  it('ignores a sensor that has stopped answering', () => {
    house(dev('s', 'sensor.temperature', 'unavailable'), dev('t', 'climate', 'unknown', { current_temperature: 70 }))
    expect(inside()).toBeNull()
  })
})
