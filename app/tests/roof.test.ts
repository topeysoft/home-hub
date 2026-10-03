// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Roofline's own pane, the roof drawn (design/roofline/DrawnC.dc.html, chosen 1 October 2026).
   These pin the drawing as the board draws it: the runs in the order they go round, each as long as its
   lights, each box where it is, the way each run leaves its box, a dark run dark where it is with its one
   next step under it -- and, before the way round is known, each box's runs drawn apart. The browser half
   is app/e2e/controller.spec.ts; this is the arithmetic it stands on. */
import { describe, expect, it } from 'vitest'
import type { Device, Roofline } from '../src/api'
import { previewRoofline } from '../src/controller'
import { dotPitch, evenOf, lookDates, roofDots, roofDrawing, roofNext, roofSentence, type Pos } from '../src/roof'

type Roof = Extract<Roofline, { exists: true }>
const roof = (kind: string) => previewRoofline(kind) as Roof
const light = (state = 'on'): Device => ({ id: 'roofline', name: 'Roofline', room_id: 'backyard', capability: 'light', state, attrs: {} })
/* Where a position lands on a line of a given width, the way the browser resolves the calc() it becomes. */
const at = (p: Pos, fixed: number, w: number) => (w - fixed) * p.f + p.px

describe('the roof, drawn in the order it goes round', () => {
  const d = roofDrawing(roof('christmas'))

  it('joins the runs in the order the house was shown, box, run, run, box, run, run, box', () => {
    expect(d.joined).toBe(true)
    expect(d.items.map(i => i.kind === 'run' ? `${i.chip}${i.run}` : `[${i.chip}]`)).toEqual(['[a]', 'a1', 'b1', '[b]', 'b2', 'c1', '[c]'])
  })

  it('draws each run as long as its lights, and nothing overlaps on a wall or a phone', () => {
    for (const w of [1272, 300]) {
      const runs = d.items.filter(i => i.kind === 'run')
      const per = runs.map(r => ((w - d.fixed) * r.w) / r.n)
      for (const p of per) expect(p).toBeCloseTo(per[0], 6)
      let end = -1
      for (const i of d.items) {
        const x = at(i.at, d.fixed, w)
        expect(x).toBeGreaterThanOrEqual(end)
        end = x + (i.kind === 'run' ? (w - d.fixed) * i.w : 22)
      }
      expect(end).toBeCloseTo(w, 6)
    }
  })

  it('says which way each run leaves its box: two of the four are turned round', () => {
    expect(d.items.filter(i => i.kind === 'run').map(i => i.kind === 'run' && i.dir)).toEqual([1, -1, 1, -1])
  })

  it('names the boxes by place under them: the ends to the ends, the middle one centered', () => {
    const boxes = d.items.filter(i => i.kind === 'box')
    expect(boxes.map(b => b.kind === 'box' && b.place)).toEqual(['Left corner', 'Right of the door', 'Garage end'])
    expect(boxes.map(b => b.kind === 'box' && b.align)).toEqual(['start', 'center', 'end'])
    expect(boxes.map(b => b.kind === 'box' && b.state)).toEqual(['Fine', 'Fine', 'Fine'])
  })

  it('rings nothing when every box answered', () => {
    expect(d.rings).toEqual([])
  })

  it('falls back to equal runs on a hub that does not say how long each one is', () => {
    const r = { ...roof('christmas'), parts: undefined }
    const runs = roofDrawing(r).items.filter(i => i.kind === 'run')
    expect(runs.map(i => i.kind === 'run' && i.n)).toEqual([103, 103, 103, 103])
  })
})

describe('a dark run, dark where it is', () => {
  const r = roof('dark')
  const d = roofDrawing(r)

  it('darkens only the garage end’s run, and rings it with its box', () => {
    expect(d.items.filter(i => i.kind === 'run' && i.dark).map(i => i.kind === 'run' && `${i.chip}${i.run}`)).toEqual(['c1'])
    expect(d.rings).toHaveLength(1)
    const ring = d.rings[0], w = 1272
    const c1 = d.items.find(i => i.kind === 'run' && i.chip === 'c')!, b2 = d.items.find(i => i.kind === 'run' && i.chip === 'b' && i.run === 2)!
    expect(at(ring.from, d.fixed, w)).toBeLessThan(at(c1.at, d.fixed, w))
    expect(at(ring.to, d.fixed, w)).toBeCloseTo(w + 14, 6)
    expect(at(ring.from, d.fixed, w)).toBeGreaterThan(at(b2.at, d.fixed, w) + (w - d.fixed) * (b2.kind === 'run' ? b2.w : 0))
    // its next step goes under it, held to the end it is at
    expect(ring.align).toBe('end')
  })

  it('darkens a box that is not answering whole, and one with its runs said only those', () => {
    const quiet = { ...r, boxes: r.boxes.map(b => b.chip === 'b' ? { ...b, state: 'Not answering' as const, sub: 'It may be unplugged, or out of reach of the Wi‑Fi.' } : b) }
    expect(roofDrawing(quiet).items.filter(i => i.kind === 'run' && i.dark).map(i => i.kind === 'run' && `${i.chip}${i.run}`)).toEqual(['b1', 'b2', 'c1'])
    const one = { ...r, boxes: r.boxes.map(b => b.chip === 'b' ? { ...b, state: 'Dark' as const, dark_runs: [2], sub: 'x' } : b) }
    expect(roofDrawing(one).items.filter(i => i.kind === 'run' && i.dark).map(i => i.kind === 'run' && `${i.chip}${i.run}`)).toEqual(['b2', 'c1'])
  })

  it('says the box’s own words under the ring -- the reason and the one thing to do', () => {
    expect(roofNext(r)).toEqual({ text: 'On a different power supply. Plug the 12 V supply back in.', wrong: true })
  })
})

describe('before the way round is known', () => {
  const d = roofDrawing(roof('ask'))

  it('draws each box with its own runs, apart, every run going away from its box', () => {
    expect(d.joined).toBe(false)
    expect(d.groups).toBe(3)
    expect(d.items.map(i => i.kind === 'run' ? `${i.chip}${i.run}${i.dir > 0 ? '>' : '<'}` : `[${i.chip}]`))
      .toEqual(['[a]', 'a1>', 'b2<', '[b]', 'b1>', '[c]', 'c1>'])
    expect(d.items.map(i => i.group)).toEqual([0, 0, 1, 1, 1, 2, 2])
    // three stretches, each a step apart from the one before
    const w = 1272
    expect(d.apart).toHaveLength(3)
    for (let g = 1; g < 3; g++) expect(at(d.apart[g].from, d.fixed, w) - at(d.apart[g - 1].to, d.fixed, w)).toBe(56)
  })

  it('asks the way round in the sentence the house already says it in', () => {
    expect(roofNext(roof('ask'))).toEqual({ text: 'Christmas goes round the house. Show it which way round?', wrong: false })
  })

  it('treats an empty order as not known', () => {
    expect(roofDrawing({ ...roof('christmas'), order: [] }).joined).toBe(false)
  })
})

describe('what the pane says about it', () => {
  it('the left column’s one sentence: what is wrong when something is, else why it is on', () => {
    expect(roofSentence(light(), roof('dark'))).toEqual({ text: 'On, but the garage end is dark.', wrong: true })
    expect(roofSentence(light(), roof('christmas'))).toEqual({ text: 'On at dusk because it keeps evenings.', wrong: false })
    expect(roofSentence(light('off'), roof('dark'))).toEqual({ text: 'Off. The garage end would stay dark.', wrong: true })
  })

  it('when every box is well, the line under the roof says so', () => {
    expect(roofNext(roof('christmas'))).toEqual({ text: 'All three are working.', wrong: false })
    const came = { ...roof('christmas'), came_on: { at: new Date('2026-12-19T16:52:00-06:00').getTime() / 1000, text: 'The roofline came on at dusk' } }
    expect(roofNext(came).text).toBe('All three were working when it came on, at 4:52 PM.')
  })

  it('the occasion’s dates, from the brain or from the occasion', () => {
    expect(lookDates(roof('christmas'))).toBe('Dec 1 – Jan 6')
    expect(lookDates({ ...roof('christmas'), occasion_dates: 'Apr 4 – 6' })).toBe('Apr 4 – 6')
    expect(lookDates(roof('none'))).toBe('')
  })

  it('its evenings, as the card heads them', () => {
    expect(evenOf(roof('christmas'))).toEqual({ name: 'On at dusk, off at 11 PM', sub: 'Every evening, like a porch light' })
    expect(evenOf({ ...roof('christmas'), evenings: 'occasion' }).sub).toBe('Only for occasions')
    expect(evenOf({ ...roof('christmas'), evenings: 'never' })).toEqual({ name: 'Not by itself', sub: 'On when somebody turns it on' })
  })
})

describe('the lights on it', () => {
  it('in the occasion’s own emitter colors, in its blocks, chasing; a dark run’s lights off', () => {
    const r = roof('dark')
    const d = roofDrawing(r)
    const dots = roofDots(d, r, 2)
    const c1 = d.items.findIndex(i => i.kind === 'run' && i.chip === 'c')
    expect(dots[c1].every(x => x.off)).toBe(true)
    const a1 = dots[1]
    expect(a1).toHaveLength(55)
    expect(a1[0].c1).toBe('rgb(255,45,36)')
    expect(a1[2].c1).toBe('rgb(20,216,96)')
    expect(a1[0].motion).toBe('chase')
  })

  it('held still, the same blocks, not moving; on an ordinary evening, its everyday warm white', () => {
    const still = roof('still')
    expect(roofDots(roofDrawing(still), still, 2)[1][0].motion).toBe('still')
    const none = roof('none')
    const dot = roofDots(roofDrawing(none), none, 2)[1][0]
    expect(dot.c1).toBe('rgb(255,199,117)')
    expect(dot.motion).toBe('still')
  })

  it('one dot for two lights on the board’s wall, and fewer where the line is shorter', () => {
    expect(dotPitch(412, 1272 - 118)).toBe(2)      // 1440x900, as DrawnC draws it
    expect(dotPitch(412, 1112 - 118)).toBe(2)      // 1280x800
    expect(dotPitch(412, 678 - 118)).toBe(4)       // the right-hand column only
    expect(dotPitch(412, 302 - 118)).toBe(11)      // a phone
  })

  it('every light dark while the roof is off', () => {
    const r = roof('christmas')
    expect(roofDots(roofDrawing(r), r, 6, false).flat().every(x => x.off)).toBe(true)
  })
})
