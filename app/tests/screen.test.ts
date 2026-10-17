// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A wall screen for a house that has a hub (design/companion/, C, chosen 7 October 2026).
   The room step is drawn in design/companion/WhereC.dc.html: each room says what is in it in a
   few words, a room that already has a screen says so, and the button names the room. */
import { describe, expect, it } from 'vitest'
import type { Device, Phone, Room } from '../src/api'
import { homeRoom, needsRoom, openOn, roomLine } from '../src/screen'

const dev = (name: string, capability: string): Device => ({ id: name, name, room_id: '', capability, state: 'off', attrs: {} })
const room = (id: string, name: string, devices: Device[] = []): Room => ({ id, name, devices, intent: 'unknown' })
const screenIn = (room: string, me = false) => ({ id: room + (me ? '-me' : ''), name: 'Hallway screen', kind: 'screen', room, me } as Phone)

describe('what each room says under its name', () => {
  it('counts the lights and names the first other thing, as the board draws it', () => {
    const hall = room('hall', 'Hallway', [dev('Ceiling', 'light'), dev('Porch', 'light'), dev('Stairs', 'light'), dev('Lamp', 'light'), dev('Front door', 'lock')])
    expect(roomLine(hall)).toBe('4 lights · door')
    expect(roomLine(room('living', 'Living room', [dev('Ceiling', 'light'), dev('TV', 'media')]))).toBe('1 light · TV')
  })
  it('names two things when there are no lights, and says so when there is nothing', () => {
    expect(roomLine(room('office', 'Office', [dev('Desk speaker', 'media'), dev('Thermostat', 'climate')]))).toBe('speaker · heating')
    expect(roomLine(room('spare', 'Spare room'))).toBe('nothing in it yet')
  })
  it('a room that already has another screen says that instead, but not for this screen itself', () => {
    const kitchen = room('kitchen', 'Kitchen', [dev('Lights', 'light')])
    expect(roomLine(kitchen, [screenIn('kitchen')])).toBe('a screen already')
    expect(roomLine(kitchen, [screenIn('kitchen', true)])).toBe('1 light')
  })
})

describe('the button names the room', () => {
  it('reads as a sentence', () => {
    expect(openOn('Hallway')).toBe('Open on the hallway')
    expect(openOn('Living room')).toBe('Open on the living room')
    expect(openOn("Jordan's room")).toBe("Open on Jordan's room")
  })
})

describe('when the room is asked', () => {
  const rooms = [room('hall', 'Hallway'), room('kitchen', 'Kitchen')]
  it('a screen with no room is asked; a phone never is', () => {
    expect(needsRoom(rooms, true, null)).toBe(true)
    expect(needsRoom(rooms, false, null)).toBe(false)
  })
  it('a screen whose room the house no longer has is asked again', () => {
    expect(needsRoom(rooms, true, 'attic')).toBe(true)
    expect(needsRoom(rooms, true, 'hall')).toBe(false)
  })
  it('before the house has loaded there is nothing to ask about', () => {
    expect(needsRoom([], true, null)).toBe(false)
  })
  it('a screen opens on, and wakes to, its own room; anything else to Home', () => {
    expect(homeRoom(rooms, true, 'kitchen')).toBe('kitchen')
    expect(homeRoom(rooms, false, 'kitchen')).toBe(null)
    expect(homeRoom(rooms, true, 'attic')).toBe(null)
  })
})
