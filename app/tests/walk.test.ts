// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Holding Shorter or Longer on a strip's pane. The numbers here are what makes this feel like
   moving the end of a strip rather than operating a repeater, so they are pinned rather than
   tuned by whoever reads the file next. design/strip/Nudge.dc.html. */
import { describe, expect, it } from 'vitest'
import { BEFORE, FASTEST, SLOWEST, gap, step, walk } from '../src/walk'

describe('holding a button walks the end', () => {
  it('moves exactly one light for a tap, whatever else it does later', () => {
    /* The whole complaint is being three lights out. If a tap cannot move one, the control does
       not answer it. */
    expect(step(0)).toBe(1)
  })

  it('waits before it starts walking, so a tap is never two lights', () => {
    expect(walk(BEFORE - 1)).toEqual([])
    expect(walk(BEFORE)).toHaveLength(1)
  })

  it('starts slowly enough that one light is still reachable by holding a moment too long', () => {
    expect(gap(0)).toBe(SLOWEST)
    expect(walk(BEFORE + 60).map(s => s.by)).toEqual([1])
  })

  it('and gets to its floor in about a second, not instantly and not eventually', () => {
    const t = walk(4000)
    const toFloor = t.findIndex((_, n) => gap(n) === FASTEST)
    expect(toFloor).toBeGreaterThan(4)
    expect(toFloor).toBeLessThan(12)
  })

  it('goes to threes only once one at a time would stop looking like motion', () => {
    expect(step(0)).toBe(1)
    expect(walk(4000).at(-1)!.by).toBe(3)
  })

  it('covers thirty lights in a hold somebody would actually hold', () => {
    /* The number that decides whether being a long way out is a hold or thirty taps. */
    const moved = walk(2000).reduce((n, s) => n + s.by, 0)
    expect(moved).toBeGreaterThanOrEqual(30)
  })

  it('never runs away: two seconds is not two hundred lights', () => {
    expect(walk(2000).reduce((n, s) => n + s.by, 0)).toBeLessThan(120)
  })
})
