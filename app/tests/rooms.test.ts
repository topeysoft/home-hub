/* The Rooms tab's arrangement: what order the house is read in, and which room
   is allowed to be big. These come out as the shape of a wall panel, so the
   first test is the one that matters -- the mock house has to land exactly
   where design/rooms/Main.dc.html drew it. */
import { describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { arrangeRooms, leadLight, playingIn, rankRooms, temperature } from '../src/rooms'

const dev = (id: string, name: string, capability: string, state: string, attrs: Record<string, any> = {}): Device =>
  ({ id, name, room_id: '', capability, state, attrs })

const room = (id: string, name: string, devices: Device[] = []): Room =>
  ({ id, name, devices: devices.map(d => ({ ...d, room_id: id })), intent: 'unknown', set_by: null, hold_until: null })

/* the house in app/mock/brain.mjs, which is the house both boards were drawn at */
const house = (): Room[] => [
  room('living', 'Living room', [
    dev('l1', 'Ceiling light', 'light', 'on', { brightness: 90 }),
    dev('l2', 'Floor lamp', 'light', 'on', { brightness: 60 }),
    dev('l3', 'Reading lamp', 'light', 'off'),
    dev('m1', 'Living room TV', 'media', 'playing', { media_title: 'The Bear' }),
    dev('s1', 'Sonos', 'media', 'paused'),
    dev('c1', 'Blinds', 'cover', 'open'),
    dev('mo1', 'Motion', 'motion', 'on'),
    dev('te1', 'Temperature', 'sensor.temperature', '73.4'),
  ]),
  room('kitchen', 'Kitchen', [
    dev('k1', 'Kitchen lights', 'light', 'on', { brightness: 255 }),
    dev('k2', 'Under-cabinet strip', 'light', 'off'),
    dev('k5', 'Back door', 'contact', 'off'),
  ]),
  room('bedroom', 'Bedroom', [
    dev('b1', 'Bedroom lamp', 'light', 'off'),
    dev('b3', 'Ceiling fan', 'fan', 'on', { percentage: 40 }),
  ]),
  room('office', 'Office', [
    dev('o1', 'Desk lamp', 'light', 'on', { brightness: 180 }),
    dev('o3', 'Office plug', 'switch', 'on'),
  ]),
  room('front', 'Front door', [
    dev('f1', 'Front door', 'lock', 'locked'),
    dev('f2', 'Doorbell', 'camera', 'streaming'),
    dev('f3', 'Porch light', 'light', 'off'),
  ]),
  room('garage', 'Garage', [
    dev('g1', 'Garage View', 'camera', 'idle'),
    dev('g2', 'Garage door', 'cover', 'closed'),
  ]),
  room('backyard', 'Backyard', [
    dev('y1', 'Backyard cam', 'camera', 'recording'),
    dev('y2', 'Robot mower', 'vacuum', 'docked'),
  ]),
  room('bath', 'Bathroom'),
  room('unassigned', 'New devices', [
    dev('u1', 'Hue color lamp 1', 'light', 'off'),
    dev('u2', 'Smart plug', 'switch', 'off'),
  ]),
]

describe('the order the house is read in', () => {
  it('lands exactly where the board drew it', () => {
    expect(rankRooms(house()).map(r => r.id)).toEqual(
      ['living', 'kitchen', 'office', 'bedroom', 'backyard', 'front', 'garage', 'bath', 'unassigned'])
  })

  it('puts what is doing something before what is merely there, and empty rooms after both', () => {
    const ids = rankRooms(house()).map(r => r.id)
    expect(ids.indexOf('bedroom')).toBeLessThan(ids.indexOf('front'))     // a fan on beats a locked door
    expect(ids.indexOf('garage')).toBeLessThan(ids.indexOf('bath'))       // a room with something in it beats an empty one
  })

  it('leaves the tray of new devices last, however much it has to ask', () => {
    const rooms = house()
    expect(rankRooms(rooms).at(-1)!.id).toBe('unassigned')
    /* even when it is the only thing in the house with anything in it at all */
    expect(rankRooms([rooms[8], rooms[7]]).map(r => r.id)).toEqual(['bath', 'unassigned'])
  })

  it('ranks a brighter room above a busier one, because that is what lighting a house means', () => {
    /* the kitchen has one lamp at 100%, the office two things on at 70%. The
       kitchen is doing more TO THE HOUSE, and a count cannot tell you that. */
    const ids = rankRooms(house()).map(r => r.id)
    expect(ids.indexOf('kitchen')).toBeLessThan(ids.indexOf('office'))
  })

  it('does not count a camera watching the porch as a room doing something', () => {
    const ids = rankRooms(house()).map(r => r.id)
    expect(ids.indexOf('backyard')).toBeLessThan(ids.indexOf('front'))    // recording is doing; streaming is watching
  })
})

describe('how much of the screen a room gets', () => {
  it('gives the house one lead and one beside it, and nothing else', () => {
    expect(arrangeRooms(house())).toEqual([
      { id: 'living', size: 'full' },
      { id: 'kitchen', size: 'half' },
      { id: 'office', size: 'third' },
      { id: 'bedroom', size: 'third' },
      { id: 'backyard', size: 'third' },
      { id: 'front', size: 'third' },
      { id: 'garage', size: 'third' },
      { id: 'bath', size: 'third' },
      { id: 'unassigned', size: 'third' },
    ])
  })

  it('fills the wall exactly: nine rooms come to twelve slots, which is four flush columns', () => {
    const slots = { full: 3, half: 2, third: 1 }
    const total = arrangeRooms(house()).reduce((n, c) => n + slots[c.size], 0)
    expect(total).toBe(12)
    expect(total % 3).toBe(0)
  })

  it('only goes full for a room with something playing in it', () => {
    /* a house where the loudest thing is a lamp does not get a poster-sized card:
       everything the room has to say fits in a half */
    const quiet = house().filter(r => r.id !== 'living')
    expect(arrangeRooms(quiet)[0]).toEqual({ id: 'kitchen', size: 'half' })
  })

  it('hands out no lead at all when nothing in the house is on', () => {
    const asleep = house().map(r => ({ ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) }))
    expect(arrangeRooms(asleep).every(c => c.size === 'third')).toBe(true)
  })

  it('survives a house of one room, and a house of none', () => {
    expect(arrangeRooms([])).toEqual([])
    expect(arrangeRooms([house()[0]])).toEqual([{ id: 'living', size: 'full' }])
  })
})

describe('what a card reads off its room', () => {
  it('finds what is playing, and ignores what is merely paused', () => {
    const [living] = house()
    expect(playingIn(living)?.id).toBe('m1')
    expect(playingIn(house()[1])).toBeUndefined()
  })

  it('finds the lamp doing the lighting rather than the first one listed', () => {
    const [living] = house()
    expect(leadLight(living)?.id).toBe('l1')                 // 90, not the floor lamp at 60
    expect(leadLight(house()[7])).toBeUndefined()            // an empty room has no lamp
  })

  it('reads a temperature only where a room owns a sensor', () => {
    expect(temperature(house()[0])).toBe('73°')
    expect(temperature(house()[1])).toBe('')                 // and says nothing rather than looking broken
  })
})
