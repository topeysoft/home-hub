// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest'
import { KIND, setupLeft, setupSteps } from '../src/band'

/* What the band shows on a phone, by kind (design/band/, chosen 2 October: line and chips). These fail
   on purpose if a line changes kind without the board changing first. */

describe('the kinds', () => {
  it('keeps a line for whatever is waiting on a person', () => {
    // A phone at the door and Needs a look are the only routes to letting a phone in and to Sign in
    // again (layout.ts); a knock keeps its line for its first hour (design/knock/).
    for (const k of ['ask', 'notes', 'knock', 'controller'] as const) expect(KIND[k]).toBe('needs')
  })
  it('makes news of what happened, a chip each', () => {
    for (const k of ['update', 'whats-new', 'move', 'waiting'] as const) expect(KIND[k]).toBe('news')
  })
  it('sends what the house would like finished to This house', () => {
    for (const k of ['passcode', 'location', 'home-screen'] as const) expect(KIND[k]).toBe('setup')
  })
})

describe('Finish setting up', () => {
  const base = { setupDone: true, locked: false, located: true, phone: true, onHomeScreen: false }

  it('counts every step that applies, done ones too, so it counts down', () => {
    const steps = setupSteps(base)
    expect(steps.map(s => s.title)).toEqual(['Set a passcode', 'Where home is', 'Add to your Home Screen'])
    expect(setupLeft(steps)).toBe(2)
  })
  it('asks for a passcode only once setup is done, as the band always did', () => {
    expect(setupSteps({ ...base, setupDone: false }).map(s => s.id)).not.toContain('passcode')
  })
  it('asks about the Home Screen only on a phone', () => {
    expect(setupSteps({ ...base, phone: false }).map(s => s.id)).not.toContain('home-screen')
  })
  it('is finished when nothing is left', () => {
    expect(setupLeft(setupSteps({ ...base, locked: true, onHomeScreen: true }))).toBe(0)
  })
})
