/* The words the house uses for what it did on its own.

   Every string here ends up on a wall in someone's kitchen, so these tests read the sentences rather
   than the shapes: a routine explained as "Sets the room to undefined" is a bug no type would catch. */
import { beforeEach, describe, expect, it } from 'vitest'
import type { Event, Routine } from '../src/api'
import { store } from '../src/store'
import { condWords, dur, explain, left, placeName, routineWords, setByLine, triggerWords } from '../src/why'

const room = (id: string, name: string, extra: Record<string, any> = {}) =>
  ({ id, name, devices: [], intent: 'unknown', set_by: null, hold_until: null, ...extra }) as any

const routine = (r: Partial<Routine>): Routine =>
  ({ id: 'r1', name: 'A routine', room: 'living', when: { motion: 'on' }, then: { intent: 'occupied' }, enabled: true, ...r }) as Routine

const event = (e: Partial<Event>): Event =>
  ({ ts: 1_757_600_000, kind: 'intent', subject: 'living', old: null, new: 'occupied', source: 'rule', detail: null, ...e }) as Event

beforeEach(() => {
  store.rooms = [room('living', 'Living room'), room('kitchen', 'Kitchen')]
  store.routines = [routine({ id: 'evening', name: 'Evening lights' })]
})

describe('lengths of time, said the way a person would', () => {
  it('counts seconds, minutes and hours without ever saying "1 minutes"', () => {
    expect(dur(1)).toBe('a second')
    expect(dur(45)).toBe('45 seconds')
    expect(dur(60)).toBe('a minute')
    expect(dur(600)).toBe('10 minutes')
    expect(dur(3600)).toBe('an hour')
    expect(dur(7200)).toBe('2 hours')
  })

  it('falls back to minutes for the awkward ones rather than "1.5 hours"', () => {
    expect(dur(5400)).toBe('90 minutes')
  })
})

describe('how long a hand-set room keeps routines out', () => {
  const now = 1_757_600_000_000

  it('says nothing at all once the hold has passed', () => {
    expect(left(now / 1000 - 10, now)).toBe('')
    expect(left(null, now)).toBe('')
    expect(left(undefined, now)).toBe('')
  })

  it('counts down in words that fit on a tile', () => {
    expect(left(now / 1000 + 30, now)).toBe('under a minute')
    expect(left(now / 1000 + 1500, now)).toBe('25 min')
    expect(left(now / 1000 + 7200, now)).toBe('2 h')
    expect(left(now / 1000 + 5400, now)).toBe('1 h 30 min')
  })
})

describe('a trigger as words', () => {
  it('reads as the present for a routine and the past for something that already happened', () => {
    expect(triggerWords({ motion: 'on' }, false)).toBe("when there's motion")
    expect(triggerWords({ motion: 'on' }, true)).toBe('motion in the room')
    expect(triggerWords({ idle: 600 }, false)).toBe('after 10 minutes of nothing')
    expect(triggerWords({ idle: 600 }, true)).toBe('no motion for 10 minutes')
  })

  it('says sunrise and sunset, and which side of them', () => {
    expect(triggerWords({ sun: 'set' }, false)).toBe('at sunset')
    expect(triggerWords({ sun: 'rise' }, false)).toBe('at sunrise')
    expect(triggerWords({ sun: 'set', offset: -1800 }, false)).toBe('30 minutes before sunset')
    expect(triggerWords({ sun: 'rise', offset: 3600 }, false)).toBe('an hour after sunrise')
  })

  it('says who came and went', () => {
    expect(triggerWords({ presence: 'somebody' }, false)).toBe('when someone comes home')
    expect(triggerWords({ presence: 'nobody' }, false)).toBe('when everyone has left')
    expect(triggerWords({ presence: 'nobody', for: 300 }, false)).toBe('when everyone has left for 5 minutes')
    expect(triggerWords({ presence: 'nobody' }, true)).toBe('everyone had left')
  })

  it('has words for a trigger it has never seen rather than printing undefined', () => {
    expect(triggerWords(undefined, false)).toBe('')
    expect(triggerWords({ somethingNew: 1 } as any, false)).toBe('')
  })
})

describe('a condition as words', () => {
  it('turns the sun into daylight and dark', () => {
    expect(condWords(['sun', 'below', 0])).toBe('after dark')
    expect(condWords(['sun', 'above', 0])).toBe('in daylight')
    expect(condWords(['sun', 'below', 10])).toBe('with the sun below 10°')
  })

  it('lists weekdays the way a sentence does', () => {
    expect(condWords(['weekday', 'in', ['mon', 'tue', 'wed']])).toBe('on Mondays, Tuesdays and Wednesdays')
    expect(condWords(['weekday', 'is', 'sat'])).toBe('on Saturdays')
    expect(condWords(['weekday', 'not', 'sun'])).toBe('except Sundays')
  })

  it('says whether the house is empty', () => {
    expect(condWords(['presence', 'is', 'nobody'])).toBe('when nobody is home')
    expect(condWords(['presence', 'is', 'somebody'])).toBe('when someone is home')
  })

  it('never throws on a condition it cannot read', () => {
    for (const c of [[], ['sun'], null, undefined, ['nonsense', 'is', 1]] as any[]) {
      expect(() => condWords(c)).not.toThrow()
      expect(condWords(c)).toBe('')
    }
  })
})

describe('a whole routine in one line', () => {
  it('reads as a sentence, capitalised, ending in a full stop', () => {
    const line = routineWords(routine({ when: { motion: 'on' }, if: [['sun', 'below', 0]], then: { intent: 'occupied' } }))
    expect(line).toBe("When there's motion, after dark. Sets the room to In use.")
  })

  it('says the whole house when that is what it means', () => {
    const line = routineWords(routine({ room: 'home', when: { presence: 'nobody', for: 300 }, then: { intent: 'away' } }))
    expect(line).toBe('When everyone has left for 5 minutes. Sets the whole house to Everything off.')
  })

  it('calls bedtime bedtime rather than Sleep when it is the whole house', () => {
    expect(routineWords(routine({ room: 'home', then: { intent: 'asleep' } }))).toContain('Bedtime')
  })

  it('names the rooms people come in through', () => {
    expect(routineWords(routine({ room: 'entry', then: { intent: 'occupied' } }))).toContain('Sets those rooms to')
  })
})

describe('naming a place', () => {
  it('says the whole house, where you come in, or the room by name', () => {
    expect(placeName('home')).toBe('the whole house')
    expect(placeName('entry')).toBe('where you come in')
    expect(placeName('kitchen')).toBe('the Kitchen')
  })

  it('falls back to the id for a room that has since gone', () => {
    expect(placeName('attic')).toBe('the attic')
  })
})

describe('the line on a room saying who set it', () => {
  const now = 1_757_600_000_000

  it('says nothing when nobody has touched it and no routine has run', () => {
    expect(setByLine(room('living', 'Living room'), now)).toBeNull()
  })

  it('credits a routine', () => {
    const line = setByLine(room('living', 'Living room', { intent: 'movie', set_by: 'rule:evening' }), now)
    expect(line).toEqual({ icon: 'sparkle', text: 'Movie · by a routine' })
  })

  it('credits a hand, and says how long routines will stay away', () => {
    const line = setByLine(room('living', 'Living room', { intent: 'movie', set_by: 'user', hold_until: now / 1000 + 3600 }), now)
    expect(line!.text).toBe('Movie · by hand, 1 h left')
  })

  it('explains a hold even when nothing set the room, so a quiet room is not a mystery', () => {
    const line = setByLine(room('living', 'Living room', { hold_until: now / 1000 + 600 }), now)
    expect(line!.text).toBe('Used by hand · routines stay out for 10 min')
  })
})

describe('one line of the log, as a sentence', () => {
  it('names the routine and says what it did and why', () => {
    const e = explain(event({ detail: JSON.stringify({ rule: 'evening', trigger: { motion: 'on' }, checked: [['sun', 'below', 0]] }) }))
    expect(e.text).toBe('Evening lights')
    expect(e.sub).toBe('The room went to In use · motion in the room · after dark')
  })

  it('owns up when a routine ran but something did not respond', () => {
    const e = explain(event({ detail: JSON.stringify({ rule: 'evening', trigger: { motion: 'on' }, failed: ['light.a'] }) }))
    expect(e.sub).toContain("one thing didn't respond")
  })

  it('does not pretend to know a routine that has since been deleted', () => {
    const e = explain(event({ detail: JSON.stringify({ rule: 'gone-now', trigger: { motion: 'on' } }) }))
    expect(e.text).toBe('A routine that has since been removed')
  })

  it('says plainly when a person did it', () => {
    const e = explain(event({ source: 'user', new: 'movie' }))
    expect(e.text).toBe('Set to Movie by hand')
  })

  it('explains a routine that was held off rather than leaving the room looking broken', () => {
    const e = explain(event({ kind: 'held', new: 'empty', detail: JSON.stringify({ rule: 'evening' }) }))
    expect(e.text).toBe('A routine wanted All off but left the room alone')
  })

  it('survives a detail that is not JSON at all', () => {
    expect(() => explain(event({ detail: '{broken' }))).not.toThrow()
    expect(explain(event({ detail: '{broken' })).text).toBeTruthy()
  })

  it('always gives something to show, whatever kind of row it is handed', () => {
    for (const kind of ['intent', 'held', 'shadowed', 'failed', 'something-new']) {
      const e = explain(event({ kind }))
      expect(e.text, kind).toBeTruthy()
      expect(e.icon, kind).toBeTruthy()
      expect(e.text, kind).not.toContain('undefined')
    }
  })
})
