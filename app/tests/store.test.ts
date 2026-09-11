/* The house as the panel understands it: what a room is doing, what a scene means, and the names
   people read off tiles. These all end up as words on a wall. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import {
  activity, cap, capsOf, currentScene, houseLine, isActive, isDead, roomActive,
  sceneHolds, scenesFor, shortName, store, visibleRooms, whatsOn,
} from '../src/store'

const dev = (id: string, name: string, capability: string, state: string, attrs: Record<string, any> = {}): Device =>
  ({ id, name, room_id: 'living', capability, state, attrs })

const room = (id: string, name: string, devices: Device[] = []): Room =>
  ({ id, name, devices: devices.map(d => ({ ...d, room_id: id })), intent: 'unknown', set_by: null, hold_until: null })

beforeEach(() => {
  store.rooms = []
  store.loaded = true
  store.error = ''
  store.presence = null
  store.homeName = 'Ash Street'
  store.rules = {}
})

describe('what a device is', () => {
  it('reads a capability without its sub-kind', () => {
    expect(cap(dev('s', 'T', 'sensor.temperature', '70'))).toBe('sensor')
    expect(cap(dev('l', 'L', 'light', 'on'))).toBe('light')
  })

  it('knows a thing that is doing something from one that is not', () => {
    expect(isActive(dev('l', 'L', 'light', 'on'))).toBe(true)
    expect(isActive(dev('m', 'M', 'media', 'playing'))).toBe(true)
    expect(isActive(dev('l', 'L', 'light', 'off'))).toBe(false)
  })

  it('knows a thing that has stopped answering', () => {
    expect(isDead(dev('l', 'L', 'light', 'unavailable'))).toBe(true)
    expect(isDead(dev('l', 'L', 'light', 'unknown'))).toBe(true)
    expect(isDead(dev('l', 'L', 'light', 'off'))).toBe(false)
  })
})

describe('names, read inside the room they are in', () => {
  const bedroom = room('bedroom', 'Bedroom')

  it('drops the room from the front of a thing named after it', () => {
    expect(shortName(dev('t', 'Bedroom TV', 'media', 'off'), bedroom)).toBe('TV')
    expect(shortName(dev('l', 'Bedroom ceiling light', 'light', 'on'), bedroom)).toBe('Ceiling light')
  })

  it('keeps a name that belongs to the thing rather than a generic one', () => {
    expect(shortName(dev('c', 'Bedroom Garage View', 'camera', 'idle'), bedroom)).toBe('Bedroom Garage View')
  })

  it('leaves a name alone outside its room', () => {
    expect(shortName(dev('t', 'Bedroom TV', 'media', 'off'), room('living', 'Living room'))).toBe('Bedroom TV')
    expect(shortName(dev('t', 'Bedroom TV', 'media', 'off'))).toBe('Bedroom TV')
  })

  it('always starts with a capital', () => {
    expect(shortName(dev('l', 'desk lamp', 'light', 'on'))).toBe('Desk lamp')
  })

  it('copes with the apostrophes a phone types', () => {
    const kids = room('kids', "Kids’ room")
    expect(shortName(dev('l', "Kids' room light", 'light', 'on'), kids)).toBe('Light')
  })
})

describe('one line about a room', () => {
  it('counts the lights that are on', () => {
    expect(activity(room('living', 'Living room', [dev('a', 'A', 'light', 'on')]))).toBe('1 light on')
    expect(activity(room('living', 'Living room', [dev('a', 'A', 'light', 'on'), dev('b', 'B', 'light', 'on')]))).toBe('2 lights on')
  })

  it('says what is playing by name when it knows', () => {
    const r = room('living', 'Living room', [dev('tv', 'TV', 'media', 'playing', { media_title: 'The Bear' })])
    expect(activity(r)).toBe('The Bear')
  })

  it('mentions an unlocked door, because that is the one worth noticing', () => {
    const r = room('front', 'Front door', [dev('l', 'Front door', 'lock', 'unlocked')])
    expect(activity(r)).toBe('Unlocked')
  })

  it('joins several things with a separator rather than a sentence', () => {
    const r = room('living', 'Living room', [dev('a', 'A', 'light', 'on'), dev('c', 'Blind', 'cover', 'open')])
    expect(activity(r)).toBe('1 light on · Blind open')
  })

  it('has something to say about a room where nothing is happening', () => {
    expect(activity(room('living', 'Living room', [dev('a', 'A', 'light', 'off')]))).toBe('Quiet')
    expect(activity(room('bath', 'Bathroom'))).toBe('Nothing here yet')
  })

  it('counts what is waiting to be put somewhere', () => {
    expect(activity(room('unassigned', 'New devices', [dev('a', 'A', 'light', 'off')]))).toBe('1 to place')
    expect(activity(room('unassigned', 'New devices', [dev('a', 'A', 'light', 'off'), dev('b', 'B', 'light', 'off')]))).toBe('2 to place')
  })

  it('does not call a room busy because a camera is plugged in', () => {
    const r = room('front', 'Front door', [dev('c', 'Doorbell', 'camera', 'streaming')])
    expect(roomActive(r)).toBe(false)
    expect(activity(r)).toBe('1 camera')
  })
})

describe('the rooms Home shows', () => {
  it('puts rooms with something in them first', () => {
    store.rooms = [room('bath', 'Bathroom'), room('living', 'Living room', [dev('a', 'A', 'light', 'on')])]
    expect(visibleRooms().map(r => r.id)).toEqual(['living', 'bath'])
  })

  it('hides New devices while there is nothing new', () => {
    store.rooms = [room('unassigned', 'New devices'), room('living', 'Living room')]
    expect(visibleRooms().map(r => r.id)).toEqual(['living'])
  })
})

describe('what is on right now', () => {
  it('leaves out the things nobody taps', () => {
    store.rooms = [room('living', 'Living room', [
      dev('l', 'Light', 'light', 'on'),
      dev('m', 'Motion', 'motion', 'on'),
      dev('c', 'Doorbell', 'camera', 'streaming'),
      dev('s', 'Temp', 'sensor.temperature', '70'),
    ])]
    expect(whatsOn().map(d => d.id)).toEqual(['l'])
  })
})

describe('the line across the top of Home', () => {
  it('says the house is quiet when nothing is on', () => {
    store.rooms = [room('living', 'Living room', [dev('l', 'L', 'light', 'off')])]
    expect(houseLine()).toBe('Ash Street is quiet.')
  })

  it('names the room when only one has something on', () => {
    store.rooms = [room('living', 'Living room', [dev('l', 'L', 'light', 'on')])]
    expect(houseLine()).toBe('Something is on in the Living room.')
  })

  it('counts the rooms when more than one does', () => {
    store.rooms = [room('living', 'Living room', [dev('l', 'L', 'light', 'on')]),
                   room('kitchen', 'Kitchen', [dev('k', 'K', 'light', 'on')])]
    expect(houseLine()).toBe('Something is on in 2 rooms.')
  })

  it('points out something left on with nobody home', () => {
    store.presence = { somebody: false, since: null, source: 'people', people: [], alarm: null }
    store.rooms = [room('living', 'Living room', [dev('l', 'L', 'light', 'on')])]
    expect(houseLine()).toBe("Nobody's home, but something is on in the Living room.")
  })

  it('says what it is doing rather than lying about a house it has not read yet', () => {
    store.loaded = false
    expect(houseLine()).toBe('Finding the house…')
    store.error = 'The hub is not answering.'
    expect(houseLine()).toBe('The hub is not answering.')
  })
})

describe('scenes', () => {
  it('only offers what the room can actually do', () => {
    const lightsOnly = room('bath', 'Bathroom', [dev('l', 'L', 'light', 'on')])
    expect(scenesFor(lightsOnly).map(s => s.id)).not.toContain('movie')
    const withTv = room('living', 'Living room', [dev('l', 'L', 'light', 'on'), dev('m', 'TV', 'media', 'off')])
    expect(scenesFor(withTv).map(s => s.id)).toContain('movie')
  })

  it('offers the house scenes only once the house has something to switch off', () => {
    store.rooms = [room('front', 'Front door', [dev('c', 'Doorbell', 'camera', 'idle')])]
    expect(scenesFor(null)).toEqual([])
    store.rooms = [room('living', 'Living room', [dev('l', 'L', 'light', 'on')])]
    expect(scenesFor(null).map(s => s.id)).toEqual(['asleep', 'away'])
  })

  it('says what each button will do, in words that match the room', () => {
    const caps = capsOf([dev('l', 'L', 'light', 'on'), dev('m', 'TV', 'media', 'off'), dev('k', 'Lock', 'lock', 'locked')])
    const sleep = scenesFor(room('living', 'Living room', [dev('l', 'L', 'light', 'on')])).find(s => s.id === 'asleep')!
    expect(sleep.hint(caps)).toBe('Lights and screens off, door locked')
  })

  it('a scene holds only while every device it touched is still where it left them', () => {
    store.rules = { asleep: [['light', 'off', {}], ['lock', 'lock', {}]] }
    const asleep = room('bed', 'Bedroom', [dev('l', 'L', 'light', 'off'), dev('k', 'Lock', 'lock', 'locked')])
    expect(sceneHolds(asleep, 'asleep')).toBe(true)
    asleep.devices[0].state = 'on'
    expect(sceneHolds(asleep, 'asleep')).toBe(false)
  })

  it('a device that has stopped answering does not break the scene it was in', () => {
    store.rules = { asleep: [['light', 'off', {}]] }
    const r = room('bed', 'Bedroom', [dev('a', 'A', 'light', 'off'), dev('b', 'B', 'light', 'unavailable')])
    expect(sceneHolds(r, 'asleep')).toBe(true)
  })

  it('a scene that touches nothing in this room does not count as holding', () => {
    store.rules = { asleep: [['lock', 'lock', {}]] }
    expect(sceneHolds(room('bath', 'Bathroom', [dev('l', 'L', 'light', 'off')]), 'asleep')).toBe(false)
  })

  it('the room shows the scene it is on only while it still matches', () => {
    store.rules = { movie: [['light', 'on', {}]] }
    const r = { ...room('living', 'Living room', [dev('l', 'L', 'light', 'on')]), intent: 'movie' }
    expect(currentScene(r)).toBe('movie')
    r.devices[0].state = 'off'
    expect(currentScene(r)).toBeNull()
  })
})
