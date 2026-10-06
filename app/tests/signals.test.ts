// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { rowsOf, preview, endsToAsk, headline, doorHint, triedLine, mark } from '../src/signals'
import { done, keepDone } from '../src/store'
import type { SignalsPage, Trying } from '../src/api'

/* What the lights tell you, held to the board the household picked (design/signal/Chosen.dc.html,
   direction A with C, 24 September). Fails on purpose if the page drifts from it. */

const page = (over: Partial<SignalsPage> = {}): SignalsPage => ({
  meanings: [
    { id: 'arriving', name: 'Someone’s arriving', kind: 'way', toward: 'house', rgb: [255, 138, 0], on: true, available: true, lights: ['Driveway strip'] },
    { id: 'leaving', name: 'Someone’s leaving', kind: 'way', toward: 'out', rgb: [30, 107, 255], on: true, available: true, lights: ['Driveway strip'] },
    { id: 'open', name: 'A door’s been left open', kind: 'call', rgb: [255, 42, 74], on: true, available: true, lights: [] },
    { id: 'done', name: 'Something’s nearly done', kind: 'fill', rgb: [0, 208, 106], on: false, available: false, lights: [] },
  ],
  own: [{ id: 'garage-open', key: 'rule:garage-open', name: 'Garage left open', kind: 'end', rgb: [30, 107, 255], on: true }],
  strips: [{ id: 'abc', online: true, house_end: null, device: 'hw-1' }],
  trying: null,
  ...over,
})

describe('the arrangement', () => {
  it('draws the house’s four first, in the board’s order, and a household’s own after them', () => {
    const { house, own } = rowsOf(page())
    expect(house.map(r => r.key)).toEqual(['arriving', 'leaving', 'open', 'done'])
    expect(own.map(r => r.key)).toEqual(['rule:garage-open'])
    expect(own.every(r => r.own) && house.every(r => !r.own)).toBe(true)
  })

  it('opens a try in place, under its row, rather than as a sheet beside the list', () => {
    const vue = readFileSync('src/SignalsPage.vue', 'utf8')
    const row = vue.indexOf('class="sig-row"'), opened = vue.indexOf('class="sig-open"'), rowEnd = vue.indexOf('</li>', opened)
    expect(row).toBeGreaterThan(-1)
    expect(opened).toBeGreaterThan(row)
    expect(rowEnd).toBeGreaterThan(opened)          // inside the row's own <li>
  })

  it('gives every row a Try, ours and theirs alike', () => {
    const vue = readFileSync('src/SignalsPage.vue', 'utf8')
    expect(vue).toContain('Show me now')
    expect(vue).toContain('Wait for the real thing')
    expect(vue.match(/class="sig-row"/g)).toHaveLength(1)   // one row template serves both groups
  })

  it('sits beside Routines in This house', () => {
    const panel = readFileSync('src/HousePanel.vue', 'utf8')
    expect(panel.indexOf("id: 'signals'")).toBeGreaterThan(panel.indexOf("id: 'routines'"))
    expect(panel.indexOf("id: 'signals'")).toBeLessThan(panel.indexOf("id: 'people'"))
  })
})

describe('the previews', () => {
  it('draws a run going the way it will go', () => {
    expect(preview('way', 'house')).toBe('way')
    expect(preview('way', 'out')).toBe('back')
    expect(preview('call')).toBe('call')
  })

  it('draws them in emitter colors, never the panel’s pastels', () => {
    for (const m of page().meanings) {
      const [r, g, b] = m.rgb
      expect(Math.min(r, g, b), `${m.id} has a washed-out channel`).toBeLessThan(60)
    }
  })
})

describe('which end is the house', () => {
  it('is asked for a run or an end, only of strips nobody has asked', () => {
    expect(endsToAsk(page(), 'way')).toEqual(['abc'])
    expect(endsToAsk(page(), 'call')).toEqual([])
    expect(endsToAsk(page({ strips: [{ id: 'abc', online: true, house_end: 'plug', device: null }] }), 'way')).toEqual([])
  })
})

describe('a try', () => {
  const t = (over: Partial<Trying>): Trying => ({ id: 'x', of: 'leaving', name: 'Someone’s leaving', how: 'watch', state: 'watching', started: 0, ends: 600, steps: [], ...over })

  it('counts down while it watches', () => {
    expect(headline(t({}), 0).sub).toBe('10 min left · go and do it')
  })

  it('says nothing showed when the chain broke before the lights', () => {
    expect(headline(t({ state: 'failed', steps: [{ key: 'decide', state: 'no', text: 'The house decided: arriving' }] })).title).toBe('Nothing showed.')
    expect(headline(t({ state: 'failed', steps: [{ key: 'decide', state: 'ok', text: 'x' }, { key: 'light:a', state: 'no', text: 'y' }] })).title).toBe('A light did not answer.')
  })

  it('marks a step the chain never reached as empty, not failed', () => {
    expect(mark('wait')).toBe('')
    expect(mark('no')).toBe('!')
  })

  it('leaves its line on its row through the same kept map as a card somebody just quieted', () => {
    for (const k of Object.keys(done)) delete done[k]
    expect(triedLine('arriving')).toBe('')
    keepDone('signal:arriving', 'everything answered', new Date(2026, 8, 24, 20, 14).getTime())
    expect(triedLine('arriving')).toMatch(/^Tried 8:14\s?pm · everything answered$/)
  })
})

describe('the door', () => {
  beforeEach(() => { for (const k of Object.keys(done)) delete done[k] })
  it('says how many of the four are on and how many are the household’s own', () => {
    expect(doorHint(page())).toBe('3 of 4 on · 1 of your own')
    expect(doorHint(null)).toBe('Arriving, leaving, a door left open')
  })
})
