// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What stays on Home (design/home-keep/, B). The first test is the board: at 7:10 on a weekday, with
   the kitchen lights and the coffee maker kept and the office plug set to Never, the row has to land
   where KeepB.dc.html drew it. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Device } from '../src/api'
import { ALWAYS_MAX, alwaysIds, homeRow, isAlways, keepAlways, offersOnHome, onHomeOf } from '../src/onhome'

const dev = (id: string, name: string, capability: string, state: string, attrs: Record<string, any> = {}): Device =>
  ({ id, name, room_id: '', capability, state, attrs })

const doorbell = dev('f2', 'Doorbell', 'camera', 'streaming')
const thermostat = dev('l7', 'Thermostat', 'climate', 'cool')
const garage = dev('g1', 'Garage View', 'camera', 'idle')
const kitchen = dev('k1', 'Kitchen lights', 'light', 'off')
const coffee = dev('k3', 'Coffee maker', 'switch', 'off')
const plug = dev('o3', 'Office plug', 'switch', 'on', { off_home: true })
const path = dev('y3', 'Walkway Pathlight Light', 'light', 'on')
const tv = dev('m1', 'Living room TV', 'media', 'playing')

const keys = (row: { key: string }[]) => row.map(c => c.key)

beforeEach(() => {
  localStorage.clear()
  for (const id of [...alwaysIds()]) keepAlways(id, false)
})

describe('the row, as KeepB.dc.html drew it', () => {
  it('puts what this screen keeps straight after the glance column, drawn off, before what is on', () => {
    keepAlways('k1', true); keepAlways('k3', true)
    const row = homeRow({ prints: [], on: [path], lead: null, glance: [doorbell, thermostat, garage], always: [kitchen, coffee], scenes: true })
    expect(keys(row)).toEqual(['f2', 'l7', 'k1', 'k3', 'y3', 'scenes', 'g1'])
    expect(row.filter(c => c.kind === 'device' && c.always).map(c => c.key)).toEqual(['k1', 'k3'])
  })

  it('a house that keeps nothing gets the row it always had', () => {
    const row = homeRow({ prints: [{ id: 'p1' }], on: [tv, path], lead: 'm1', glance: [doorbell, thermostat], always: [], scenes: true })
    expect(keys(row)).toEqual(['print:p1', 'm1', 'f2', 'l7', 'y3', 'scenes'])
  })

  it('a kept thing that is on is shown once, in its kept place', () => {
    const lit = { ...kitchen, state: 'on' }
    const row = homeRow({ prints: [], on: [path, lit], lead: null, glance: [doorbell, thermostat], always: [lit], scenes: true })
    expect(keys(row)).toEqual(['f2', 'l7', 'k1', 'y3', 'scenes'])
  })

  it('a kept speaker that is playing stays the tall first card', () => {
    keepAlways('m1', true)
    const row = homeRow({ prints: [], on: [tv], lead: 'm1', glance: [doorbell, thermostat], always: [tv], scenes: false })
    expect(keys(row)).toEqual(['m1', 'f2', 'l7'])
  })

  it('Never wins over Always, because another screen may have said it since', () => {
    keepAlways('o3', true)
    expect(onHomeOf(plug)).toBe('never')
    const row = homeRow({ prints: [], on: [], lead: null, glance: [doorbell, thermostat], always: [plug], scenes: false })
    expect(keys(row)).toEqual(['f2', 'l7'])
  })
})

describe('Always, kept on this screen', () => {
  it('is remembered across a reload, in the order it was kept', () => {
    keepAlways('k3', true); keepAlways('k1', true)
    expect(JSON.parse(localStorage.getItem('home-always')!)).toEqual(['k3', 'k1'])
    expect(isAlways('k1')).toBe(true)
    expect(onHomeOf(kitchen)).toBe('always')
  })

  it('refuses a fifth rather than letting the oldest go unasked', () => {
    for (let i = 0; i < ALWAYS_MAX; i++) expect(keepAlways(`d${i}`, true)).toBe(true)
    expect(keepAlways('d9', true)).toBe(false)
    expect(alwaysIds()).toEqual(['d0', 'd1', 'd2', 'd3'])
    keepAlways('d1', false)
    expect(keepAlways('d9', true)).toBe(true)
  })

  it('is When it is on for anything never chosen', () => {
    expect(onHomeOf(path)).toBe('on')
  })
})

it('is not offered on what is always on Home, or never can be', () => {
  for (const k of ['camera', 'climate', 'sensor', 'motion', 'appliance']) expect(offersOnHome(k)).toBe(false)
  for (const k of ['light', 'switch', 'fan', 'media', 'cover', 'lock']) expect(offersOnHome(k)).toBe(true)
})
