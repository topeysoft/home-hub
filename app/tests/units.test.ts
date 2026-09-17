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
