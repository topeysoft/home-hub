/* Sensors are read, not tapped. One line above a room's tiles, so the words have to be short and right. */
import { describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { isReading, readingLabel, readingName, readingOn } from '../src/readings'

const dev = (name: string, capability: string, state: string, attrs: Record<string, any> = {}): Device =>
  ({ id: 'x', name, room_id: 'living', capability, state, attrs })
const room = (name: string): Room => ({ id: 'living', name, devices: [], intent: 'unknown', set_by: null, hold_until: null })

describe('which things are read rather than tapped', () => {
  it('counts sensors, motion and doors, and nothing a person switches', () => {
    expect(isReading(dev('T', 'sensor.temperature', '70'))).toBe(true)
    expect(isReading(dev('M', 'motion', 'off'))).toBe(true)
    expect(isReading(dev('D', 'contact', 'on'))).toBe(true)
    expect(isReading(dev('L', 'light', 'on'))).toBe(false)
    expect(isReading(dev('C', 'camera', 'idle'))).toBe(false)
  })
})

describe('what a sensor says', () => {
  it('rounds a temperature and gives it a degree sign', () => {
    expect(readingLabel(dev('T', 'sensor.temperature', '68.4'))).toBe('68°')
    expect(readingLabel(dev('T', 'sensor.temperature', '68.6'))).toBe('69°')
  })

  it('marks humidity as a percentage and light in lux', () => {
    expect(readingLabel(dev('H', 'sensor.humidity', '51'))).toBe('51%')
    expect(readingLabel(dev('L', 'sensor.illuminance', '120'))).toBe('120 lx')
  })

  it('says motion and doors in words rather than on and off', () => {
    expect(readingLabel(dev('M', 'motion', 'on'))).toBe('Motion')
    expect(readingLabel(dev('M', 'motion', 'off'))).toBe('No motion')
    expect(readingLabel(dev('D', 'contact', 'on'))).toBe('Open')
    expect(readingLabel(dev('D', 'contact', 'off'))).toBe('Closed')
  })

  it('says so plainly when a sensor has stopped reporting', () => {
    expect(readingLabel(dev('T', 'sensor.temperature', 'unavailable'))).toBe('Not responding')
    expect(readingLabel(dev('T', 'sensor.temperature', 'unknown'))).toBe('Not responding')
  })

  it('passes a reading through rather than printing NaN when it is not a number', () => {
    expect(readingLabel(dev('T', 'sensor.temperature', 'calibrating'))).toBe('calibrating')
  })
})

describe('whether a reading is worth naming', () => {
  it('drops a name that only repeats what the reading already says', () => {
    expect(readingName(dev('Motion', 'motion', 'on'), room('Living room'))).toBe('')
    expect(readingName(dev('Living room motion', 'motion', 'on'), room('Living room'))).toBe('')
  })

  it('keeps a name that says where in the room it is', () => {
    expect(readingName(dev('Under the stairs', 'motion', 'on'), room('Hallway'))).toBe('Under the stairs')
  })

  it('keeps the name of a door, because which door it is matters', () => {
    expect(readingName(dev('Back door', 'contact', 'on'), room('Kitchen'))).toBe('Back door')
  })
})

describe('a reading that lights up', () => {
  it('is motion seen or a door standing open, and never a temperature', () => {
    expect(readingOn(dev('M', 'motion', 'on'))).toBe(true)
    expect(readingOn(dev('M', 'motion', 'off'))).toBe(false)
    expect(readingOn(dev('D', 'contact', 'on'))).toBe(true)
    expect(readingOn(dev('T', 'sensor.temperature', '90'))).toBe(false)
  })
})
