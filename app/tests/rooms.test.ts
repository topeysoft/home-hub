/* The Rooms tab's arrangement: what order the house is read in, and which room
   is allowed to be big. These come out as the shape of a wall panel, so the
   first test is the one that matters -- the mock house has to land exactly
   where design/rooms/Main.dc.html drew it. */
import { describe, expect, it } from 'vitest'
import type { Device, Room } from '../src/api'
import { arrangeRooms, leadLight, playingIn, rankRooms, temperature, tracks } from '../src/rooms'

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

  it('fills the wall exactly: nine rooms come to sixty tracks, which is four flush columns', () => {
    /* the grid is fifteen tracks deep, and the four sizes are spans of it: a
       third is five, which is what a third of a three-track column always was */
    const slots = { full: 15, half: 10, third: 5, row: 3 }
    const total = arrangeRooms(house()).reduce((n, c) => n + slots[c.size], 0)
    expect(total).toBe(60)
    expect(total % 15).toBe(0)
  })

  it('only goes full for a room with something playing in it', () => {
    /* a house where the loudest thing is a lamp does not get a poster-sized card:
       everything the room has to say fits in a half */
    const quiet = house().filter(r => r.id !== 'living')
    expect(arrangeRooms(quiet)[0]).toEqual({ id: 'kitchen', size: 'half' })
  })

  it('hands out no lead at all when nothing in the house is on', () => {
    const asleep = house().map(r => ({ ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) }))
    expect(arrangeRooms(asleep).some(c => c.size === 'full' || c.size === 'half')).toBe(false)
  })
})

/* The index: the quiet end of the house, which on a big one is most of it. The
   rule these all circle is the same one -- whole columns or nothing -- because a
   column with three rows and a hole under them reads as a bug, not a list.
   design/rooms/QuietIndex.dc.html. */
describe('the quiet end of the house', () => {
  it('leaves a house with too few quiet rooms exactly as it was', () => {
    /* four quiet rooms is less than a column, so there is no index to make and
       the mock house lands where design/rooms/Main.dc.html drew it */
    expect(arrangeRooms(house()).some(c => c.size === 'row')).toBe(false)
  })

  it('makes rows only in whole columns of five, and keeps the remainder as cards', () => {
    const asleep = house().map(r => ({ ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) }))
    const plan = arrangeRooms(asleep)
    /* nine quiet rooms: one column of five rows, and the four highest-ranked
       stay cards rather than leaving a hole at the bottom of a second column */
    expect(plan.filter(c => c.size === 'row')).toHaveLength(5)
    expect(plan.filter(c => c.size === 'third')).toHaveLength(4)
    expect(plan.slice(4).every(c => c.size === 'row')).toBe(true)   // and they are the tail
  })

  it('gives the lead the full column when the index has made room for one', () => {
    /* An evening where the television is paused and most of the house is off.
       The old rule said half -- nothing is playing -- and it was right to,
       because every card behind it wanted the width. With seven quiet rooms
       gone to an index there is a column going spare, and the Living room has
       two lamps, a blind and motion to spend it on. */
    const evening = house().map(r =>
      r.id === 'living' ? { ...r, devices: r.devices.map(d => d.id === 'm1' ? { ...d, state: 'paused' } : d) }
      : ['kitchen', 'office', 'bedroom'].includes(r.id) ? { ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) }
      : r)
    const plan = arrangeRooms(evening)
    expect(plan.filter(c => c.size === 'row')).toHaveLength(5)
    expect(plan[0]).toEqual({ id: 'living', size: 'full' })
  })

  it('still refuses the lead a full column when it has one thing to say', () => {
    /* one lamp in one room is one line, and one line does not want a poster --
       the index makes room, it does not hand it out */
    const oneLamp = house().map(r =>
      r.id === 'living' ? { ...r, devices: [{ ...r.devices[0], state: 'on' }] }
      : ['kitchen', 'office', 'bedroom', 'backyard'].includes(r.id) ? { ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) }
      : r)
    const plan = arrangeRooms(oneLamp)
    expect(plan.filter(c => c.size === 'row').length).toBeGreaterThan(0)
    expect(plan[0]).toEqual({ id: 'living', size: 'half' })
  })

  it('places every row on a track of its own so the columns cannot interleave', () => {
    const asleep = house().map(r => ({ ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) }))
    const at = tracks(arrangeRooms(asleep)).map(t => t.at)
    expect(at.slice(0, 4)).toEqual([undefined, undefined, undefined, undefined])
    expect(at.slice(4)).toEqual([1, 4, 7, 10, 13])                  // one column, top to bottom
  })

  it('starts the next column over rather than running past the foot of one', () => {
    const many = Array.from({ length: 10 }, (_, i) => room(`q${i}`, `Room ${i}`, [dev(`d${i}`, 'Lamp', 'light', 'off')]))
    const at = tracks(arrangeRooms(many)).map(t => t.at).filter(n => n !== undefined)
    expect(at).toEqual([1, 4, 7, 10, 13, 1, 4, 7, 10, 13])
  })

  it('stretches the last card to the foot of its column, so no row can backfill the hole', () => {
    /* three rooms on and twelve quiet: the cards come to fifty tracks, which is
       three columns and five tracks of sky. That sky is where `column dense`
       would put the index's first row, and the index would run short from there
       to its end. The last card takes it instead. */
    const big = [...house(), ...Array.from({ length: 6 }, (_, i) =>
      room(`x${i}`, `Room ${i}`, [dev(`e${i}`, 'Lamp', 'light', 'off')]))]
      .map(r => ['living', 'kitchen', 'backyard'].includes(r.id) ? r
        : { ...r, devices: r.devices.map(d => ({ ...d, state: 'off' })) })
    const plan = arrangeRooms(big)
    const t = tracks(plan)
    const cards = plan.filter(c => c.size !== 'row').length
    const spans = t.slice(0, cards).reduce((n, x) => n + x.span, 0)
    expect(spans % 15).toBe(0)                                      // whole columns, always
    expect(t[cards - 1].span).toBeGreaterThan(5)                    // and the last card paid for it
  })

  it('leaves a flush wall alone rather than stretching a card that already fits', () => {
    const t = tracks(arrangeRooms(house()))
    expect(t.map(x => x.span)).toEqual([15, 10, 5, 5, 5, 5, 5, 5, 5])
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
