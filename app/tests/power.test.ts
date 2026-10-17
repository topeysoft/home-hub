// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The house's power (design/energy/, B with C's sun): said in the band only when it changes what somebody would
   do, and the sun in the weather drawing warming with what the roof is making. These are the board's words;
   change the board first (design/energy/SaysB.dc.html), then this, then power.ts. */
import { describe, expect, it } from 'vitest'
import type { Power } from '../src/api'
import { KIND } from '../src/band'
import { aboutHours, flowWords, fullIn, lasted, powerBand, powerSentence, warmth } from '../src/power'

const afternoon: Power = { solar: 5.8, house: 1.2, battery: 2.4, grid: -2.2, charge: 84, reserve: 20, grid_up: true, left: 24.1,
                           has_battery: true, spare: false, out_since: null, back: null }
const band = (p: Power | null) => powerBand(p).map(l => [l.title, l.sub, l.needs])

describe('the house\'s power in the band', () => {
  it('says nothing on an ordinary afternoon, however much the roof is making', () => {
    expect(band(afternoon)).toEqual([])
    expect(band(null)).toEqual([])
    expect(band({ ...afternoon, solar: 0, battery: -0.9, charge: 21 })).toEqual([])   // the battery at its reserve at night is the system working
  })

  it('sun to spare, once the brain has seen the battery full and power going out for ten minutes', () => {
    expect(band({ ...afternoon, spare: true, charge: 100 })).toEqual([['Sun to spare', 'The battery is full: a good time for the dryer or the car', false]])
    expect(band({ ...afternoon, spare: true, has_battery: false, charge: null })).toEqual([['Sun to spare', 'A good time for the dryer or the car', false]])
  })

  it('the power out is a line of its own, with how long the battery should carry the house', () => {
    const out = { ...afternoon, solar: 0, house: 1.7, battery: -1.7, grid: 0, grid_up: false, out_since: 1 }
    expect(band(out)).toEqual([['The power is out — the battery has the house', '84%, about 14 hours as things are', true]])
    expect(band({ ...out, charge: 18, left: 5.1, house: 1.6 })).toEqual([['The battery is getting low', '18% left, and the power is still out', true]])
    expect(band({ ...out, has_battery: false, charge: null, left: null })).toEqual([['The power is out', 'The grid is down', true]])
    expect(KIND['power-out']).toBe('needs')
    expect(KIND.power).toBe('news')
  })

  it('the power back, and for how long it was out', () => {
    expect(band({ ...afternoon, back: { at: 0, lasted: 7800 } })).toEqual([['The power is back', 'It was out for 2 hours 10 minutes', false]])
    expect(lasted(3600)).toBe('1 hour')
    expect(lasted(20)).toBe('less than a minute')
  })
})

describe('how long, said the way somebody would', () => {
  it('rounds to what is worth knowing', () => {
    expect([aboutHours(30), aboutHours(14.2), aboutHours(1), aboutHours(0.6), aboutHours(0.01)])
      .toEqual(['more than a day', 'about 14 hours', 'about an hour', 'about 35 minutes', 'about 5 minutes'])
  })
})

describe('the pane', () => {
  it('says what the power is doing in a sentence', () => {
    expect(powerSentence(afternoon)).toBe('The sun is making more than the house needs. The battery is charging and should be full in about 2 hours; the rest is going to the grid.')
    expect(powerSentence({ ...afternoon, solar: 0.6, house: 1.4, battery: -0.8, grid: 0 })).toBe('The sun is making some of what the house needs, and the battery is making up the rest.')
    expect(powerSentence({ ...afternoon, solar: 0, battery: -0.9, charge: 62 })).toBe('The battery has the house, at 62%.')
    expect(powerSentence({ ...afternoon, grid_up: false, solar: 0, house: 1.7 })).toBe('The power is out. The battery has the house, and should last about 14 hours as things are.')
  })

  it('names each circle in the picture', () => {
    expect(flowWords(afternoon)).toEqual({ sun: '5.8 kW', house: 'using 1.2 kW', battery: '84%, charging', grid: 'sending 2.2 kW' })
    expect(flowWords({ ...afternoon, grid_up: false }).grid).toBe('Out')
    expect(fullIn({ ...afternoon, charge: 100 })).toBe('')
  })
})

describe('the sun in the weather drawing', () => {
  it('warms with the roof against the most it has made this month, and is untouched without one', () => {
    expect(warmth(null, 7.9)).toBe(0)
    expect(warmth(0, 7.9)).toBe(0)
    expect(warmth(7.9, 7.9)).toBe(1)
    expect(warmth(5.8, 7.9)).toBeCloseTo(0.73, 2)
    expect(warmth(5.8, null)).toBe(1)
  })
})
