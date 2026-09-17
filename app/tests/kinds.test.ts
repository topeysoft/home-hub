/* What a thing IS, when the house has it wrong: docs/kinds.md.

   A lamp on a smart plug is a `switch` to the driver -- and Home Assistant is not wrong, it IS a switch.
   It is also, in the only sense the person living there cares about, a light. On this side that is one
   question: does the panel draw and name the thing by what its owner said, everywhere, and never by the
   raw field the brain picks a service from. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { activityParts, cap, capsOf, iconFor, shownAs, store, whatsOn } from '../src/store'
import { paneKind, reading, verbs } from '../src/pane'

const plug = (kind?: string, state = 'on'): Device =>
  ({ id: 'switch.porch', name: 'Porch lamp', room_id: 'living', capability: 'switch', state, attrs: {}, kind })

const room = (...devices: Device[]): Room =>
  ({ id: 'living', name: 'Living room', devices, intent: 'occupied', set_by: null, hold_until: null })

beforeEach(() => { store.rooms = []; store.loaded = true; store.rules = {}; store.homeName = 'Ash Street' })

describe('what the panel treats a thing as', () => {
  it('takes the owner at their word where they have given one', () => {
    expect(cap(plug('light'))).toBe('light')
    expect(cap(plug())).toBe('switch')
  })
  it('leaves the driver’s own word alone underneath, because that is what picks the service', () => {
    expect(plug('light').capability).toBe('switch')
  })
  it('draws it with the instrument and the verbs of what it is shown as', () => {
    expect(paneKind(plug('light'))).toBe('light')
    expect(verbs(plug('light')).some(v => v.id === 'power')).toBe(true)
  })
  it('reads it as what it is shown as: a plug that is a lamp says On, not nothing', () => {
    expect(reading(plug('light', 'on'))).toBe('On')       // no brightness to quote: it is still a plug
    expect(reading(plug('light', 'off'))).toBe('Off')
  })
})

describe('the room it is in', () => {
  it('counts it among the lights once somebody has said so', () => {
    expect(activityParts(room(plug('light')))).toEqual(['1 light on'])
    expect(capsOf([plug('light')]).has('light')).toBe(true)
  })
  it('names it as the plug it is until they do', () => {
    expect(activityParts(room(plug()))).toEqual(['Porch lamp on'])
  })
  it('still shows up under what is on either way', () => {
    store.rooms = [room(plug('light'))]
    expect(whatsOn().map(d => d.id)).toEqual(['switch.porch'])
  })
})

describe('a siren, once somebody has said it is one', () => {
  const siren = (kind?: string, state = 'off'): Device =>
    ({ id: 'switch.siren', name: 'Siren', room_id: 'living', capability: 'switch', state, attrs: {}, kind })

  it('says what it is doing to a house, not what it is doing to a circuit', () => {
    expect(reading(siren('alarm', 'on'))).toBe('Sounding')
    expect(reading(siren('alarm'))).toBe('Silent')
    expect(reading(siren('alarm', 'on'))).not.toBe('On')
  })
  it('offers to sound and to silence, in those words', () => {
    const power = (d: Device) => verbs(d).find(v => v.id === 'power')
    expect(power(siren('alarm'))?.label).toBe('Sound it')
    expect(power(siren('alarm', 'on'))?.label).toBe('Silence it')
  })
  it('gets the plug’s one-control instrument, because that is all it is underneath', () => {
    expect(paneKind(siren('alarm'))).toBe('alarm')
  })
  it('is what a room says first: a siren is not what a room is doing, it is what it is shouting', () => {
    expect(activityParts(room(siren('alarm', 'on'), plug('light')))).toEqual(['Alarm sounding', '1 light on'])
  })
  it('says nothing at all while it is silent', () => {
    expect(activityParts(room(siren('alarm')))).toEqual([])
  })
  it('is on the strip of what is on, where one tap silences it', () => {
    store.rooms = [room(siren('alarm', 'on'))]
    expect(whatsOn().map(d => d.id)).toEqual(['switch.siren'])
  })
  it('says so quietly on its own pane', () => {
    expect(shownAs(siren('alarm'))).toBe('Shown as an alarm')
  })
})

describe('saying so', () => {
  it('says it quietly, in the panel’s own words', () => {
    expect(shownAs(plug('light'))).toBe('Shown as a light')
    expect(shownAs(plug('fan'))).toBe('Shown as a fan')
  })
  it('says nothing at all where nobody has disagreed with the driver', () => {
    expect(shownAs(plug())).toBe('')
    expect(shownAs({ ...plug(), kind: 'switch' })).toBe('')
  })
})

describe('an appliance, guessed from its name and said over', () => {
  const ice = (kind?: string, state = 'on'): Device =>
    ({ id: 'switch.ice', name: 'Refrigerator Ice Maker', room_id: 'living', capability: 'switch', state, attrs: {}, kind, guess: 'appliance', hw: 'hw-fridge', hw_name: 'Refrigerator' })

  it('is shown as the house’s guess until somebody says otherwise', () => {
    expect(cap(ice())).toBe('appliance')
    expect(cap(ice('switch'))).toBe('switch')
    expect(cap(ice('light'))).toBe('light')
  })
  it('says nothing under its name while it is only a guess, and “Shown as a plug” once somebody disagreed', () => {
    expect(shownAs(ice())).toBe('')
    expect(shownAs(ice('switch'))).toBe('Shown as a plug')
  })
  it('reads On and Off, and offers the one button', () => {
    expect(reading(ice())).toBe('On')
    expect(reading(ice(undefined, 'off'))).toBe('Off')
    expect(verbs(ice()).some(v => v.id === 'power')).toBe(true)
    expect(paneKind(ice())).toBe('appliance')
  })
  it('is not a plug the room counts, and not news the house puts under what is on', () => {
    expect(activityParts(room(ice(), plug()))).toEqual(['Porch lamp on'])
    store.rooms = [room(ice(), plug())]
    expect(whatsOn().map(d => d.id)).toEqual(['switch.porch'])
  })
  it('wears the snowflake for ice, and the machine for anything else', () => {
    expect(iconFor(ice())).toBe('snow')
    expect(iconFor({ ...ice(), name: 'Dishwasher Delay Start' })).toBe('appliance')
    expect(iconFor(plug())).toBe('switch')
  })
})
