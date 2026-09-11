/* What the house will do next on its own. The line reads "Next: Porch light, 7:12 PM", so being an
   hour out is worse than saying nothing. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Routine } from '../src/api'
import { store } from '../src/store'
import { nextRun, upcoming, upcomingLine } from '../src/upcoming'

const routine = (r: Partial<Routine>): Routine =>
  ({ id: 'r1', name: 'A routine', room: 'living', when: { time: '19:00' }, then: { intent: 'occupied' }, enabled: true, ...r }) as Routine

// A Friday, so the weekday tests have somewhere to stand.
const friday = new Date(2026, 8, 11, 12, 0)

beforeEach(() => {
  store.routines = []
  store.ambient = { location: { name: 'Chicago', lat: 41.88, lon: -87.63 }, weather: null }
})

describe('a routine that runs by the clock', () => {
  it('fires at its time later the same day', () => {
    const at = nextRun(routine({ when: { time: '19:00' } }), friday)!
    expect(at.getDate()).toBe(11)
    expect(at.getHours()).toBe(19)
  })

  it('waits for tomorrow once the time today has gone', () => {
    const at = nextRun(routine({ when: { time: '08:00' } }), friday)!
    expect(at.getDate()).toBe(12)
    expect(at.getHours()).toBe(8)
  })

  it('skips to the next day it is allowed to run', () => {
    const weekend = routine({ when: { time: '08:00' }, if: [['weekday', 'in', ['sat', 'sun']]] })
    const at = nextRun(weekend, friday)!
    expect(at.getDay()).toBe(6)             // Saturday
    expect(at.getDate()).toBe(12)
  })

  it('honours a single day and an excluded one', () => {
    expect(nextRun(routine({ when: { time: '08:00' }, if: [['weekday', 'is', 'mon'] ] }), friday)!.getDay()).toBe(1)
    expect(nextRun(routine({ when: { time: '08:00' }, if: [['weekday', 'not', 'sat'] ] }), friday)!.getDay()).not.toBe(6)
  })

  it('says nothing at all for a routine that is switched off', () => {
    expect(nextRun(routine({ when: { time: '19:00' }, enabled: false }), friday)).toBeNull()
  })
})

describe('a routine that runs by the sun', () => {
  it('finds the next sunset', () => {
    const at = nextRun(routine({ when: { sun: 'set' } }), friday)!
    expect(at.getDate()).toBe(11)
    expect(at.getHours()).toBe(19)          // Chicago sunset on 11 September is just after seven
  })

  it('applies an offset, so "half an hour before sunset" is half an hour before', () => {
    const plain = nextRun(routine({ when: { sun: 'set' } }), friday)!
    const early = nextRun(routine({ when: { sun: 'set', offset: -1800 } }), friday)!
    expect((plain.getTime() - early.getTime()) / 60000).toBeCloseTo(30, 0)
  })

  it('finds the next sunrise, which is tomorrow when the sun is already up', () => {
    const at = nextRun(routine({ when: { sun: 'rise' } }), friday)!
    expect(at.getDate()).toBe(12)
  })

  it('has no answer for a house that has not been told where it is', () => {
    store.ambient = { location: null, weather: null }
    expect(nextRun(routine({ when: { sun: 'set' } }), friday)).toBeNull()
  })
})

describe('a routine with no time of its own', () => {
  it('is left out, because "after 20 minutes of nothing" is not a time', () => {
    expect(nextRun(routine({ when: { idle: 1200 } }), friday)).toBeNull()
    expect(nextRun(routine({ when: { motion: 'on' } }), friday)).toBeNull()
    expect(nextRun(routine({ when: { presence: 'nobody' } }), friday)).toBeNull()
  })
})

describe('the next thing the house will do', () => {
  it('picks the soonest of them', () => {
    store.routines = [routine({ id: 'late', name: 'Late', when: { time: '23:00' } }),
                      routine({ id: 'soon', name: 'Soon', when: { time: '13:00' } })]
    expect(upcoming(friday)!.routine.id).toBe('soon')
  })

  it('says nothing when the next one is more than a day away', () => {
    store.routines = [routine({ when: { time: '13:00' }, if: [['weekday', 'is', 'wed']] })]
    expect(upcoming(friday)).toBeNull()
    expect(upcomingLine(friday)).toBe('')
  })

  it('says nothing when the house has no routines at all', () => {
    expect(upcoming(friday)).toBeNull()
    expect(upcomingLine(friday)).toBe('')
  })

  it('reads as a line a person can act on, and marks tomorrow as tomorrow', () => {
    store.routines = [routine({ name: 'Porch light', when: { time: '19:00' } })]
    expect(upcomingLine(friday)).toMatch(/^Next: Porch light, \d{1,2}:\d{2}/)

    store.routines = [routine({ name: 'Morning', when: { time: '08:00' } })]
    expect(upcomingLine(friday)).toContain('tomorrow')
  })
})
