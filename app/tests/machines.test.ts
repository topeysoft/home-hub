/* A machine and its features: a fridge is one thing in the kitchen, not four plugs. machines.ts. */
import { describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { featureName, machineName, machinesOf } from '../src/machines'

const feature = (id: string, name: string, extra: Partial<Device> = {}): Device =>
  ({ id, name, room_id: 'kitchen', capability: 'switch', state: 'on', attrs: {}, guess: 'appliance', hw: 'hw-fridge', hw_name: 'Refrigerator', ...extra })
const kitchen: Room = { id: 'kitchen', name: 'Kitchen', devices: [], intent: 'occupied' }

describe('which devices are one machine', () => {
  it('groups appliance features that share a unit, and leaves everything else where it was', () => {
    const lamp: Device = { id: 'light.k', name: 'Kitchen light', room_id: 'kitchen', capability: 'light', state: 'on', attrs: {} }
    const { machines, rest } = machinesOf([lamp, feature('switch.ice', 'Refrigerator Ice Maker'), feature('switch.bites', 'Refrigerator Ice Bites')])
    expect(machines.map(m => [m.key, m.name, m.devices.map(d => d.id)])).toEqual([['machine:hw-fridge', 'Refrigerator', ['switch.ice', 'switch.bites']]])
    expect(rest.map(d => d.id)).toEqual(['light.k'])
  })
  it('does not make a card of one row: a machine with a single feature stays a tile', () => {
    const { machines, rest } = machinesOf([feature('switch.delay', 'Dishwasher Delay Start', { hw: 'hw-dw', hw_name: 'Dishwasher' })])
    expect(machines).toEqual([])
    expect(rest.map(d => d.id)).toEqual(['switch.delay'])
  })
  it('is about what the thing is SHOWN as: two plugs on one strip are not a machine, and a feature said to be a plug leaves the card', () => {
    const plugs = [feature('switch.a', 'Strip A', { guess: null, hw: 'hw-strip' }), feature('switch.b', 'Strip B', { guess: null, hw: 'hw-strip' })]
    expect(machinesOf(plugs).machines).toEqual([])
    const { machines } = machinesOf([feature('switch.ice', 'Refrigerator Ice Maker'), feature('switch.bites', 'Refrigerator Ice Bites'), feature('switch.cool', 'Refrigerator Power Cool', { kind: 'switch' })])
    expect(machines[0].devices.map(d => d.id)).toEqual(['switch.ice', 'switch.bites'])
  })
  it('keeps two different machines apart', () => {
    const { machines } = machinesOf([
      feature('switch.ice', 'Refrigerator Ice Maker'), feature('switch.bites', 'Refrigerator Ice Bites'),
      feature('switch.w1', 'Washer Steam', { hw: 'hw-w', hw_name: 'Washer' }), feature('switch.w2', 'Washer Extra Rinse', { hw: 'hw-w', hw_name: 'Washer' }),
    ])
    expect(machines.map(m => m.name)).toEqual(['Refrigerator', 'Washer'])
  })
})

describe('what it is called', () => {
  it('is what the driver calls the unit', () => {
    expect(machineName([feature('a', 'Refrigerator Ice Maker'), feature('b', 'Refrigerator Ice Bites')])).toBe('Refrigerator')
  })
  it('falls back to the words the features share, then to a plain word', () => {
    expect(machineName([feature('a', 'Samsung Fridge Ice Maker', { hw_name: null }), feature('b', 'Samsung Fridge Power Cool', { hw_name: null })])).toBe('Samsung Fridge')
    expect(machineName([feature('a', 'Ice Maker', { hw_name: null }), feature('b', 'Power Cool', { hw_name: null })])).toBe('Appliance')
  })
  it('names a feature on its card without the machine’s name in front of it', () => {
    expect(featureName(feature('a', 'Refrigerator Ice Maker'), 'Refrigerator', kitchen)).toBe('Ice Maker')
    expect(featureName(feature('a', 'Power Cool'), 'Refrigerator', kitchen)).toBe('Power Cool')
    expect(featureName(feature('a', 'Refrigerator'), 'Refrigerator', kitchen)).toBe('Refrigerator')
  })
})
