// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A switch with a motion sensor built in is one thing on the wall: docs/units.md, units.ts. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { store } from '../src/store'
import { eyeOf, onATile, partWord, renameParts, seeing, sensorName, unitName, unitsOf } from '../src/units'

const light = (id = 'light.gl', extra: Partial<Device> = {}): Device =>
  ({ id, name: 'Garage Left Light Light', room_id: 'unassigned', capability: 'light', state: 'off', attrs: { motion: 'binary_sensor.gl' }, hw: 'hw-gl', hw_name: 'Garage Left Light', named_by_unit: true, ...extra })
const motion = (id = 'binary_sensor.gl', extra: Partial<Device> = {}): Device =>
  ({ id, name: 'Garage Left Light Motion', room_id: 'unassigned', capability: 'motion', state: 'on', attrs: {}, hw: 'hw-gl', hw_name: 'Garage Left Light', named_by_unit: true, ...extra })
const plug: Device = { id: 'switch.plug', name: 'Smart plug', room_id: 'unassigned', capability: 'switch', state: 'off', attrs: {}, hw: 'hw-plug' }
const room = (...devices: Device[]): Room => ({ id: 'yard', name: 'Backyard', devices, intent: 'occupied' })

beforeEach(() => { store.rooms = [] })

describe('the rows New devices shows', () => {
  it('makes one row of a light and the motion sensor on the same hardware, led by the light', () => {
    const rows = unitsOf([motion(), light(), plug])
    expect(rows.map(r => [r.key, r.name, r.lead.id, r.parts.length])).toEqual([['unit:hw-gl', 'Garage Left Light', 'light.gl', 2], ['switch.plug', 'Smart plug', 'switch.plug', 1]])
  })
  it('leaves a thing on its own hardware, or on none, as a row of its own', () => {
    const bare: Device = { id: 'light.x', name: 'Lamp', room_id: 'unassigned', capability: 'light', state: 'off', attrs: {} }
    expect(unitsOf([bare, plug]).map(r => r.key)).toEqual(['light.x', 'switch.plug'])
  })
  it('names the unit after the hardware, else after its lead part', () => {
    expect(unitName([motion(), light()])).toBe('Garage Left Light')
    expect(unitName([motion('m', { hw_name: null }), light('l', { hw_name: null })])).toBe('Garage Left Light Light')
  })
  it('says what the parts are in a word each, and keeps a part somebody named themselves', () => {
    expect(partWord(light(), 'Garage Left Light')).toBe('Light')
    expect(partWord(motion(), 'Garage Left Light')).toBe('Motion')
    expect(partWord(motion('m', { name: 'Steps' }), 'Garage Left Light')).toBe('Steps')
    expect(partWord(motion('m', { name: 'Garage Left Light' }), 'Garage Left Light')).toBe('Motion')
  })
})

describe('renaming the unit on the panel, before the house confirms', () => {
  it('carries parts named after the old name, and leaves the ones HA names for it to HA', () => {
    const l = light('l', { named_by_unit: false }), m = motion('m', { named_by_unit: false, name: 'Steps' }), h = motion('h')
    renameParts([l, m, h], 'Garage Left Light', 'Left garage')
    expect([l.name, m.name, h.name]).toEqual(['Left garage Light', 'Steps', 'Garage Left Light Motion'])
    expect([l.hw_name, m.hw_name, h.hw_name]).toEqual(['Left garage', 'Left garage', 'Left garage'])
  })
})

describe('the room', () => {
  it('lets a light see through its own sensor', () => {
    const l = light(), m = motion()
    store.rooms = [room(l, m)]
    expect(eyeOf(l)?.id).toBe('binary_sensor.gl')
    expect(seeing(l)).toBe(true)
    m.state = 'off'
    expect(seeing(l)).toBe(false)
    expect(seeing(plug)).toBe(false)
  })
  it('keeps the sensor off the strip while its light is a tile here, and on it when the light is elsewhere', () => {
    const l = light(), m = motion()
    expect(onATile(m, room(l, m))).toBe(true)
    expect(onATile(m, room(m))).toBe(false)
    expect(onATile(l, room(l, m))).toBe(false)
  })
  it('names a sensor that stays on the strip without its unit in front', () => {
    expect(sensorName(motion(), room())).toBe('Motion')
    expect(sensorName(motion('m', { name: 'Back steps' }), room())).toBe('Back steps')
  })
})

describe('what a part is called on its tile', () => {
  it('is the unit’s name when HA has only added the kind to it, and its own name otherwise', async () => {
    const { shortName } = await import('../src/store')
    expect(shortName(light(), room())).toBe('Garage Left Light')
    expect(shortName(light('l', { name: 'Garage Left Light Light', hw_name: null }), room())).toBe('Garage Left Light Light')
    expect(shortName(light('l', { name: 'Steps' }), room())).toBe('Steps')
    expect(shortName(light('l', { name: 'Backyard Pathlight Light', hw_name: 'Backyard Pathlight' }), room())).toBe('Backyard Pathlight')   // the room's name comes off only where a generic word is left, as ever: "Backyard Light" would be Light, this stays whole
  })
})

describe('what a rename from the pane renames', () => {
  it('is the unit when the thing is named after it, and only the thing when it is a feature or alone', async () => {
    const { renamesUnit } = await import('../src/units')
    const l = light(), m = motion()
    store.rooms = [room(l, m)]
    expect(renamesUnit(l)).toBe(true)
    expect(renamesUnit(m)).toBe(false)                                    // "Garage Left Light Motion" is a sensor, not the unit
    const ice: Device = { ...l, id: 'switch.ice', name: 'Refrigerator Ice Maker', capability: 'switch', hw: 'hw-f', hw_name: 'Refrigerator' }
    store.rooms = [room(ice, { ...ice, id: 'switch.bites', name: 'Refrigerator Ice Bites' })]
    expect(renamesUnit(ice)).toBe(false)
    store.rooms = [room(l)]
    expect(renamesUnit(l)).toBe(false)                                    // alone on its hardware: nothing else to carry
  })
})

describe('a fan with a light in it', () => {
  const fan = (leads = 'fan', extra: Partial<Device> = {}): Device =>
    ({ id: 'fan.bed', name: 'Bedroom Fan', room_id: 'bed', capability: 'fan', state: 'on', attrs: { percentage: 40, light: 'light.bed', leads }, hw: 'hw-fan', hw_name: 'Bedroom Fan', ...extra })
  const lamp = (leads = 'fan', extra: Partial<Device> = {}): Device =>
    ({ id: 'light.bed', name: 'Bedroom Fan Light', room_id: 'bed', capability: 'light', state: 'off', attrs: { fan: 'fan.bed', leads }, hw: 'hw-fan', hw_name: 'Bedroom Fan', ...extra })
  const bed = (...devices: Device[]): Room => ({ id: 'bed', name: 'Bedroom', devices, intent: 'occupied' })

  it('is one tile: the fan leads by default and the light rides on it', async () => {
    const { isCarried, leadsFixture, partnerOf } = await import('../src/units')
    const f = fan(), l = lamp()
    store.rooms = [bed(f, l)]
    expect(partnerOf(f)?.id).toBe('light.bed')
    expect(partnerOf(l)?.id).toBe('fan.bed')
    expect([leadsFixture(f), leadsFixture(l)]).toEqual([true, false])
    expect([isCarried(f, store.rooms[0]), isCarried(l, store.rooms[0])]).toEqual([false, true])
  })
  it('swaps when the owner says the light leads', async () => {
    const { isCarried, leadsFixture } = await import('../src/units')
    const f = fan('light'), l = lamp('light')
    store.rooms = [bed(f, l)]
    expect([leadsFixture(f), leadsFixture(l)]).toEqual([false, true])
    expect([isCarried(f, store.rooms[0]), isCarried(l, store.rooms[0])]).toEqual([true, false])
  })
  it('gives the carried part its own tile back when its lead is not in the room', async () => {
    const { isCarried } = await import('../src/units')
    const l = lamp()
    store.rooms = [bed(l)]
    expect(isCarried(l, store.rooms[0])).toBe(false)
  })
  it('is still a light to the room and to the house', async () => {
    const { activityParts, whatsOn } = await import('../src/store')
    const f = fan(), l = lamp('fan', { state: 'on' })
    store.rooms = [bed(f, l)]
    expect(activityParts(store.rooms[0])).toEqual(['1 light on', 'Fan on'])   // "Bedroom Fan" is "Fan" inside the Bedroom, as ever
    expect(whatsOn().map(d => d.id).sort()).toEqual(['fan.bed', 'light.bed'])
  })
  it('keeps the light’s full name when it leads, so the tile under a lamp drawing does not say Fan', async () => {
    const { shortName } = await import('../src/store')
    expect(shortName(lamp('light'), bed())).toBe('Bedroom Fan Light')
    expect(shortName(fan(), bed())).toBe('Fan')
  })
  it('says a fan’s speed in a word', async () => {
    const { speedWord } = await import('../src/units')
    expect(speedWord(fan())).toBe('Low')
    expect(speedWord(fan('fan', { attrs: { percentage: 66 } }))).toBe('Medium')
    expect(speedWord(fan('fan', { attrs: { percentage: 100 } }))).toBe('High')
    expect(speedWord(fan('fan', { attrs: {} }))).toBe('On')
    expect(speedWord(fan('fan', { state: 'off' }))).toBe('Off')
  })
  it('offers each part the other on its pane, whichever leads', async () => {
    const { verbs } = await import('../src/pane')
    const f = fan(), l = lamp()
    store.rooms = [bed(f, l)]
    expect(verbs(f).map(v => v.id)).toContain('lamp')
    expect(verbs(l).map(v => v.id)).toContain('fan')
  })
})
