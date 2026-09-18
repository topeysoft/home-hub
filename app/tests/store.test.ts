// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The house as the panel understands it: what a room is doing, what a scene means, and the names
   people read off tiles. These all end up as words on a wall. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Device, Room } from '../src/api'
import {
  activity, cap, capsOf, currentScene, doneLine, forgetDone, houseLine, isActive, isDead, justDone, newBuild,
  perform, reloadOnto, restingLine, restingParts, roomActive, sayUpdated, sceneHolds, scenesFor, shortName, store,
  updateReady, visibleRooms, whatsOn,
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

/* What a room says when it is doing nothing, which on a big house is most of
   the Rooms tab. "Quiet" on ten cards is the absence of a sentence written out
   ten times; design/rooms/Main.dc.html drew the room's resting state instead. */
describe('what a room says at rest', () => {
  it('says what the room is holding rather than that it is holding nothing', () => {
    const r = room('front', 'Front door', [
      dev('l', 'Front door', 'lock', 'locked'),
      dev('c', 'Doorbell', 'camera', 'idle'),
      dev('p', 'Porch light', 'light', 'off'),
    ])
    expect(activity(r)).toBe('Quiet')                                  // the three home layouts, unchanged
    expect(restingLine(r)).toBe('Locked · Camera watching')
  })

  it('leads with what is being KEPT, because that is what a quiet room is checked for', () => {
    const r = room('garage', 'Garage', [
      dev('t', 'Garage TV', 'media', 'off'),
      dev('d', 'Garage door', 'cover', 'closed'),
      dev('c', 'Garage View', 'camera', 'idle'),
    ])
    expect(restingParts(r)).toEqual(['Blind closed', 'Camera watching'])
  })

  it('stops at two, because a third phrase on a third of a card is an ellipsis', () => {
    const r = room('den', 'Den', [
      dev('l', 'Den door', 'lock', 'locked'),
      dev('c', 'Blind', 'cover', 'closed'),
      dev('m', 'Den TV', 'media', 'off'),
      dev('a', 'A', 'light', 'off'), dev('b', 'B', 'light', 'off'),
    ])
    expect(restingParts(r)).toHaveLength(2)
    expect(restingLine(r)).toBe('Locked · Blind closed')
  })

  it('names the one screen and counts the rest', () => {
    const one = room('den', 'Den', [dev('m', 'Den TV', 'media', 'off')])
    expect(restingLine(one)).toBe('TV off')                            // shortName drops the room it is in
    const two = room('den', 'Den', [dev('m', 'TV', 'media', 'off'), dev('n', 'Projector', 'media', 'off')])
    expect(restingLine(two)).toBe('2 screens off')
  })

  it('never claims a door is locked when only some of them are', () => {
    const r = room('side', 'Side', [
      dev('a', 'Front', 'lock', 'locked'), dev('b', 'Back', 'lock', 'unlocked')])
    expect(restingLine(r)).toBe('Unlocked')                            // and that is activity's word, not a resting one
  })

  it('leaves a room that is doing something exactly as it reads today', () => {
    const r = room('living', 'Living room', [dev('a', 'A', 'light', 'on'), dev('c', 'Blind', 'cover', 'open')])
    expect(restingLine(r)).toBe(activity(r))
  })

  it('has nothing to add to an empty room, or to the tray', () => {
    expect(restingLine(room('bath', 'Bathroom'))).toBe('Nothing here yet')
    expect(restingLine(room('unassigned', 'New devices', [dev('a', 'A', 'light', 'off')]))).toBe('1 to place')
  })

  it('falls back to the old word when the room has nothing it can describe', () => {
    const r = room('hall', 'Hall', [dev('s', 'Back door', 'contact', 'off')])
    expect(restingLine(r)).toBe('Quiet')
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

/* What you have just done, still on the screen. A thing you quiet leaves `whatsOn` at once -- it is not
   on any more -- and Home would have closed the row over the card under the finger that tapped it. So the
   panel remembers what it did instead, and every layout draws from this one map; only the panel looking
   away empties it. See `done` in store.ts, and App.vue for the three moments that count as looking away. */
describe('what you have just done', () => {
  beforeEach(() => {
    forgetDone(true)
    vi.stubGlobal('fetch', async () => ({ ok: true, status: 200 }) as unknown as Response)
  })
  afterEach(() => { forgetDone(true); vi.unstubAllGlobals() })

  const lamp = () => {
    store.rooms = [room('living', 'Living room', [dev('l', 'Lamp', 'light', 'on')])]
    return store.rooms[0].devices[0]
  }

  it('keeps a thing it has just quieted, though it is not on any more', async () => {
    await perform(lamp(), 'off', undefined, { state: 'off' })
    expect(whatsOn()).toEqual([])
    expect(justDone().map(d => d.id)).toEqual(['l'])
    expect(doneLine('l')).toBe('Off · just now')
  })

  it('says what it did, not just that it did something', async () => {
    store.rooms = [room('front', 'Front door', [dev('b', 'Blind', 'cover', 'open'), dev('k', 'Door', 'lock', 'unlocked')])]
    const [blind, door] = store.rooms[0].devices
    await perform(blind, 'close', undefined, { state: 'closed' })
    await perform(door, 'lock', undefined, { state: 'locked' })
    expect(doneLine('b').startsWith('Closed')).toBe(true)
    expect(doneLine('k').startsWith('Locked')).toBe(true)
  })

  it('takes it back the moment the thing is on again, which is what the card\'s second tap does', async () => {
    const l = lamp()
    await perform(l, 'off', undefined, { state: 'off' })
    await perform(l, 'on', undefined, { state: 'on' })
    expect(justDone()).toEqual([])
    expect(whatsOn().map(d => d.id)).toEqual(['l'])
  })

  it('holds it while the panel is being looked at, and drops it when it is not', async () => {
    await perform(lamp(), 'off', undefined, { state: 'off' })
    forgetDone()                     // the half-hour sweep, with the card a second old
    expect(justDone().map(d => d.id)).toEqual(['l'])
    forgetDone(true)                 // at rest, or gone behind another app
    expect(justDone()).toEqual([])
  })
})

describe('an update the hub should raise by itself', () => {
  const update = (u: Record<string, any>) => { store.status = { update: u } as any; store.updating = false }

  it('is offered when there is one and nothing is already installing it', () => {
    update({ available: true, offer: true, requested: false, state: null })
    expect(updateReady()).toBe(true)
  })

  it('goes quiet once the install has been asked for', () => {
    update({ available: true, offer: true, requested: true, state: null })
    expect(updateReady()).toBe(false)
    update({ available: true, offer: true, requested: false, state: { state: 'running' } })
    expect(updateReady()).toBe(false)
  })

  it('does not nudge for a version that was installed and put back', () => {
    /* `available` is still true -- there really is a newer build, and This hub still offers the
       button. What stops is the hub pushing it at somebody who has already been through it once. */
    update({ available: true, offer: false, rejected: '1.3.0', requested: false, state: { state: 'reverted', bad: 'v1.3.0' } })
    expect(updateReady()).toBe(false)
  })

  it('says nothing at all when the hub cannot tell', () => {
    update({ available: null, offer: null, requested: false, state: null })
    expect(updateReady()).toBe(false)
  })
})

describe('the page follows the hub onto a new build', () => {
  /* Until it reloads, the page is the old build, however new the brain is. */
  it('is a new build when the version the hub answers with changes', () => {
    expect(newBuild('v0.3.0', 'v0.3.1')).toBe(true)
    expect(newBuild('main-2cd5f50', 'main-411844d')).toBe(true)
  })

  it('is not one on the first answer, on the same answer, or on a working copy', () => {
    expect(newBuild(undefined, 'v0.3.1')).toBe(false)     // the page just loaded: this is the build it is
    expect(newBuild('v0.3.1', 'v0.3.1')).toBe(false)
    expect(newBuild('dev', 'dev')).toBe(false)
    expect(newBuild('v0.3.0', 'dev')).toBe(false)         // somebody started a working copy; vite reloads that itself
    expect(newBuild('v0.3.0', undefined)).toBe(false)     // an older brain that does not say
  })

  it('reloads, and the page after it says what happened', () => {
    const kept: Record<string, string> = {}
    vi.stubGlobal('sessionStorage', { setItem: (k: string, v: string) => { kept[k] = v }, getItem: (k: string) => kept[k] ?? null, removeItem: (k: string) => { delete kept[k] } })
    const reload = vi.fn(); vi.stubGlobal('location', { reload })
    reloadOnto('v0.3.1')
    expect(reload).toHaveBeenCalledTimes(1)
    store.toast = null
    sayUpdated()
    expect(store.toast?.text).toBe('Updated to v0.3.1.')
    store.toast = null
    sayUpdated()                                            // once: the next load of the page is not an update
    expect(store.toast).toBeNull()
    vi.unstubAllGlobals()
  })

  it('still reloads where nothing can be kept', () => {
    vi.stubGlobal('sessionStorage', { setItem: () => { throw new Error('private') }, getItem: () => { throw new Error('private') }, removeItem: () => {} })
    const reload = vi.fn(); vi.stubGlobal('location', { reload })
    reloadOnto('v0.3.1')
    expect(reload).toHaveBeenCalledTimes(1)
    expect(() => sayUpdated()).not.toThrow()
    vi.unstubAllGlobals()
  })
})
