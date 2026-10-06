// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Telling one new device from another before a room is picked for it: telling.ts, SortView.vue. */
import { describe, expect, it } from 'vitest'
import type { Account, Device } from '../src/api'
import { unitsOf } from '../src/units'
import { blinkWord, canBlink, known, knownOf, makerWord, nowOf, nowWord } from '../src/telling'

const dev = (extra: Partial<Device> = {}): Device =>
  ({ id: 'light.wiz_abc', name: 'Wiz RGBW Tunable ABC123', room_id: 'unassigned', capability: 'light', state: 'off', attrs: {}, ...extra })
const account = (id: string, kind: string): Account =>
  ({ id, kind, name: kind, state: 'on', why: '', flow: null, things: 1 })

describe('the maker, without the words that belong to a registrar', () => {
  it('drops the legal suffix and keeps the name people know', () => {
    expect(makerWord('Signify Netherlands B.V.')).toBe('Signify Netherlands')
    expect(makerWord('TP-Link Corporation Limited')).toBe('TP-Link')
    expect(makerWord('Shelly Europe Ltd')).toBe('Shelly Europe')
    expect(makerWord('Brilliant')).toBe('Brilliant')
  })
  it('keeps the whole thing rather than leave nothing behind', () => {
    expect(makerWord('Limited')).toBe('Limited')      // a maker actually called that still gets said
    expect(makerWord(null)).toBe('')
  })
})

describe('what the house knows besides the name', () => {
  it('names the account somebody signed into, then the model', () => {
    const d = dev({ entry: 'e1', maker: 'Signify Netherlands B.V.', model: 'Hue color lamp' })
    expect(knownOf(d, { e1: account('e1', 'Philips Hue') })).toEqual(['Philips Hue', 'Hue color lamp'])
  })
  it('keeps the maker off the line where an account already says where it came from', () => {
    /* "Signify Netherlands B.V." is a name off a certificate. It tells a person nothing and pushes the
       model -- the half that differs between two rows -- off the end of the line. */
    const d = dev({ entry: 'e1', maker: 'Signify Netherlands B.V.' })
    expect(knownOf(d, { e1: account('e1', 'Philips Hue') })).toEqual(['Philips Hue'])
  })
  it('says the maker where nobody signed into anything, which is what a radio brings', () => {
    expect(knownOf(dev({ maker: 'TP-Link Corporation Limited', model: 'HS100' }))).toEqual(['TP-Link', 'HS100'])
  })
  it('lets a model that already names its maker say it once', () => {
    expect(knownOf(dev({ maker: 'Brilliant', model: 'Brilliant Smart Dimmer Switch' }))).toEqual(['Brilliant Smart Dimmer Switch'])
    const d = dev({ entry: 'e1', maker: 'Brilliant', model: 'Brilliant' })
    expect(knownOf(d, { e1: account('e1', 'Brilliant') })).toEqual(['Brilliant'])
  })
  it('is empty where the house knows nothing more than the name', () => {
    expect(knownOf(dev())).toEqual([])
    expect(known(unitsOf([dev()])[0])).toBe('')
  })
  it('reads the unit off its lead part, not off the sensor beside it', () => {
    const light = dev({ id: 'light.gl', hw: 'hw-gl', hw_name: 'Garage Left', maker: 'Ring', model: 'Smart Lighting Pathlight' })
    const motion = dev({ id: 'binary_sensor.gl', capability: 'motion', hw: 'hw-gl', hw_name: 'Garage Left' })
    expect(known(unitsOf([motion, light])[0])).toBe('Ring · Smart Lighting Pathlight')
  })
})

describe('how a thing stands, where that helps tell it apart', () => {
  it('says On now, because a person can look up and see which lamp is lit', () => {
    expect(nowOf(dev({ state: 'on' }))).toEqual({ text: 'On now', live: true })
  })
  it('says a thing is not answering, which is why blinking it would show nobody anything', () => {
    expect(nowOf(dev({ state: 'unavailable' }))).toEqual({ text: 'Not answering', live: false })
  })
  it('says nothing about off, which every other row is too', () => {
    expect(nowOf(dev())).toBeNull()
    expect(nowWord(unitsOf([dev()])[0])).toBeNull()
  })
})

describe('what can be asked to show itself', () => {
  const row = (d: Device) => unitsOf([d])[0]
  it('offers a light, a switch and a fan, in their own words', () => {
    expect(blinkWord(row(dev()))).toBe('Blink it')
    expect(blinkWord(row(dev({ capability: 'switch' })))).toBe('Flash it')
    expect(blinkWord(row(dev({ capability: 'fan' })))).toBe('Spin it')
  })
  it('never offers a camera or a lock a button that cannot work', () => {
    expect(canBlink(row(dev({ capability: 'camera' })))).toBe(false)
    expect(canBlink(row(dev({ capability: 'lock' })))).toBe(false)
    expect(canBlink(row(dev({ capability: 'cover' })))).toBe(false)
  })
  it('never offers it on a thing that is not answering', () => {
    expect(canBlink(row(dev({ state: 'unavailable' })))).toBe(false)
    expect(canBlink(row(dev()))).toBe(true)
  })
  it('reads the driver word and not what the owner shows it as: a lamp on a plug is still a switch', () => {
    expect(canBlink(row(dev({ capability: 'switch', kind: 'light' })))).toBe(true)
    expect(blinkWord(row(dev({ capability: 'switch', kind: 'light' })))).toBe('Blink it')
  })
})
