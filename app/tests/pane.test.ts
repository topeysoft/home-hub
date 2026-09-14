/* What an opened device says about itself: the one reading, the verbs it really has, the facts the
   house actually holds, and the day it has had. The words on a pane somebody reads from a doorway. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device, Event, Room } from '../src/api'
import { store } from '../src/store'
import { facts, moment, moments, paneKind, reading, verbs, whyLine } from '../src/pane'

const dev = (id: string, name: string, capability: string, state: string, attrs: Record<string, any> = {}, maker?: string): Device =>
  ({ id, name, room_id: 'living', capability, state, attrs, maker })

const room = (intent = 'occupied', hold: number | null = null): Room =>
  ({ id: 'living', name: 'Living room', devices: [], intent, set_by: null, hold_until: hold })

const ev = (kind: string, newv: string | null, ts: number, source = 'device', detail?: any): Event =>
  ({ ts, kind, subject: 'x', old: null, new: newv, source, detail: detail ? JSON.stringify(detail) : null })

const NOW = new Date('2026-09-13T19:40:00').getTime()
const at = (h: number, m: number) => new Date(`2026-09-13T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`).getTime() / 1000

beforeEach(() => { store.rooms = [] })

describe('which instrument a kind gets', () => {
  it('gives the three that only watch the same one', () => {
    expect(paneKind(dev('a', 'Motion', 'motion', 'on'))).toBe('sense')
    expect(paneKind(dev('b', 'Temperature', 'sensor.temperature', '73'))).toBe('sense')
    expect(paneKind(dev('c', 'Back door', 'contact', 'off'))).toBe('sense')
  })
  it('keeps every kind that can be told to do something apart', () => {
    for (const k of ['light', 'media', 'climate', 'cover', 'lock', 'camera', 'fan', 'switch', 'vacuum'])
      expect(paneKind(dev('d', 'X', k, 'on'))).toBe(k)
  })
})

describe('the one reading', () => {
  it('says how bright rather than that it is on', () => {
    expect(reading(dev('l', 'Lamp', 'light', 'on', { brightness: 90 }))).toBe('35%')
    expect(reading(dev('l', 'Lamp', 'light', 'on'))).toBe('On')
    expect(reading(dev('l', 'Lamp', 'light', 'off', { brightness: 90 }))).toBe('Off')
  })
  it('says what is playing, not that something is', () => {
    expect(reading(dev('m', 'TV', 'media', 'playing', { media_title: 'The Bear' }))).toBe('The Bear')
    expect(reading(dev('m', 'TV', 'media', 'playing'))).toBe('Playing')
  })
  it('never prints a raw state string at a person', () => {
    /* What shipped before: "locked", "recording", "docked" -- lower-case, straight out of the driver. */
    expect(reading(dev('k', 'Front door', 'lock', 'locked'))).toBe('Locked')
    expect(reading(dev('c', 'Cam', 'camera', 'recording'))).toBe('Recording')
    expect(reading(dev('v', 'Mower', 'vacuum', 'docked'))).toBe('Docked')
    expect(reading(dev('v', 'Mower', 'vacuum', 'cleaning'))).toBe('Out working')
  })
  it('reads a blind as how open it is', () => {
    expect(reading(dev('b', 'Blinds', 'cover', 'open', { current_position: 70 }))).toBe('70% open')
    expect(reading(dev('g', 'Garage door', 'cover', 'closed'))).toBe('Shut')
  })
  it('reads a thermostat as the room, in the house unit', () => {
    expect(reading(dev('t', 'Thermostat', 'climate', 'cool', { current_temperature: 73.6 }), '°F')).toBe('74°F')
  })
  it('says a thing is not answering before anything else', () => {
    expect(reading(dev('l', 'Lamp', 'light', 'unavailable', { brightness: 200 }))).toBe('Not answering')
  })
})

describe('the verbs a kind really has', () => {
  const ids = (d: Device) => verbs(d).map(v => v.id)
  it('offers power only to things that have an on and an off', () => {
    expect(ids(dev('l', 'Lamp', 'light', 'on'))).toContain('power')
    expect(ids(dev('s', 'Plug', 'switch', 'off'))).toContain('power')
    expect(ids(dev('t', 'Thermostat', 'climate', 'cool'))).toContain('power')
  })
  it('offers it to none of the four the brain would refuse', () => {
    /* act(id, 'on') has no entry in SERVICE for these, so the pane used to answer 400 at a person. */
    for (const k of ['lock', 'cover', 'camera', 'vacuum'])
      expect(ids(dev('x', 'X', k, 'on'))).not.toContain('power')
  })
  it('gives a camera its own picture and the floodlight built into it', () => {
    store.rooms = [{ ...room(), devices: [dev('y1l', 'Cam light', 'light', 'off')] }]
    expect(ids(dev('y1', 'Cam', 'camera', 'recording', { light: 'y1l' }))).toEqual(['watch', 'lamp', 'why', 'edit'])
    expect(ids(dev('g1', 'Garage cam', 'camera', 'idle'))).toEqual(['watch', 'why', 'edit'])
  })
  it('always ends with why and rename, whatever the kind', () => {
    for (const k of ['light', 'media', 'climate', 'cover', 'lock', 'fan', 'switch', 'vacuum', 'motion'])
      expect(ids(dev('x', 'X', k, 'on')).slice(-2)).toEqual(['why', 'edit'])
  })
})

describe('the facts, and only the ones the house holds', () => {
  it('leaves out what it does not know rather than printing a blank row', () => {
    expect(facts(dev('l', 'Lamp', 'light', 'on', { brightness: 90 }), room())).toEqual([])
    expect(facts(dev('l', 'Lamp', 'light', 'on', { color_temp_kelvin: 2700 }), room(), '°F')
      .map(f => `${f.k}: ${f.v}`)).toEqual(['Warmth: 2700K'])
  })
  it('carries the maker when the registry knew one', () => {
    expect(facts(dev('l', 'Lamp', 'light', 'on', {}, 'Philips Hue'), room())).toEqual([{ k: 'Made by', v: 'Philips Hue' }])
  })
  it('adds what the room as a whole is doing, which is why a lamp went off on its own', () => {
    expect(facts(dev('l', 'Lamp', 'light', 'off'), room('movie'))).toEqual([{ k: 'The room is on', v: 'Movie' }])
    expect(facts(dev('l', 'Lamp', 'light', 'off'), room('occupied'))).toEqual([])
  })
  it('tells a thermostat by its humidity, its target and where it is reading from', () => {
    const t = dev('t', 'Thermostat', 'climate', 'cool', { current_humidity: 48, temperature: 71, current_temperature: 74 })
    expect(facts(t, room(), '°F').map(f => f.k)).toEqual(['Humidity', 'Asked for', 'Sensing'])
  })
  it('never shows more than four', () => {
    const m = dev('m', 'TV', 'media', 'playing', { media_position: 1421, media_duration: 3740, volume_level: 0.35, app_name: 'Disney+' }, 'Sony')
    expect(facts(m, room('movie')).length).toBe(4)
  })
})

describe('what it did today', () => {
  it('turns an action the hub took into a sentence, with who did it', () => {
    expect(moment(ev('action', 'off', at(19, 2), 'user'), dev('l', 'Lamp', 'light', 'on'), NOW))
      .toEqual({ when: '7:02 PM', text: 'Switched off, by hand' })
  })
  it('reads a dimmer change off the detail the log kept', () => {
    const e = ev('action', 'on', at(19, 2), 'user', { brightness_pct: 35 })
    expect(moment(e, dev('l', 'Lamp', 'light', 'on'), NOW)?.text).toBe('On at 35%, by hand')
  })
  it('says what a thermostat was asked for, in the house unit', () => {
    const e = ev('action', 'set', at(18, 40), 'user', { temperature: 71 })
    expect(moment(e, dev('t', 'T', 'climate', 'cool'), NOW, '°F')?.text).toBe('Asked for 71°F, by hand')
  })
  it('claims no author for a state change, because the driver never says who', () => {
    expect(moment(ev('state', 'on', at(18, 12)), dev('l', 'Lamp', 'light', 'on'), NOW))
      .toEqual({ when: '6:12 PM', text: 'On' })
  })
  it('says a timer did it when a timer did', () => {
    expect(moment(ev('action', 'off', at(19, 30), 'timer'), dev('s', 'Plug', 'switch', 'off'), NOW)?.text)
      .toBe('Switched off, by its timer')
  })
  it('speaks each kind in its own words', () => {
    expect(moment(ev('state', 'on', at(19, 38)), dev('mo', 'Motion', 'motion', 'on'), NOW)?.text).toBe('Movement')
    expect(moment(ev('state', 'off', at(16, 12)), dev('c', 'Back door', 'contact', 'off'), NOW)?.text).toBe('Shut')
    expect(moment(ev('state', 'cleaning', at(14, 0)), dev('v', 'Mower', 'vacuum', 'docked'), NOW)?.text).toBe('Went out')
  })
  it('drops the rows that say nothing and keeps the newest few', () => {
    const d = dev('l', 'Lamp', 'light', 'on')
    const rows = [ev('intent', 'movie', at(19, 0)), ev('state', 'on', at(18, 12)), ev('action', 'off', at(13, 40), 'user'),
                  ev('state', null, at(12, 0)), ev('state', 'off', at(11, 0)), ev('state', 'on', at(10, 0))]
    expect(moments(rows, d, 3, NOW).map(m => m.text)).toEqual(['On', 'Switched off, by hand', 'Off'])
  })
})

describe('why it is like that', () => {
  it('is this thing\'s last move, said plainly', () => {
    const d = dev('l', 'Lamp', 'light', 'on')
    expect(whyLine(d, [ev('state', 'on', at(18, 12))], room(), NOW)).toBe('On at 6:12 PM.')
  })
  it('adds the room when routines are being kept out of it', () => {
    const d = dev('l', 'Lamp', 'light', 'on')
    const held = room('occupied', NOW / 1000 + 3600)
    expect(whyLine(d, [ev('action', 'on', at(19, 2), 'user')], held, NOW))
      .toBe('Switched on, by hand at 7:02 PM. Routines are staying out of this room for now.')
  })
  it('says plainly when a thing has stopped answering', () => {
    const d = dev('l', 'Lamp', 'light', 'unavailable')
    expect(whyLine(d, [ev('state', 'unavailable', at(15, 0))], room(), NOW)).toBe('Lamp has not answered since 3:00 PM.')
  })
})
