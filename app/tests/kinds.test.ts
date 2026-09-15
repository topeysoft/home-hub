/* What a thing IS, when the house has it wrong: docs/kinds.md.

   A lamp on a smart plug is a `switch` to the driver -- and Home Assistant is not wrong, it IS a switch.
   It is also, in the only sense the person living there cares about, a light. On this side that is one
   question: does the panel draw and name the thing by what its owner said, everywhere, and never by the
   raw field the brain picks a service from. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { activityParts, cap, capsOf, shownAs, store, whatsOn } from '../src/store'
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
