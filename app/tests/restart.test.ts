// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The minute the hub is gone.
 *
 * A restart is the one thing this panel does that destroys the thing doing it, so the waiting IS the
 * feature: a number that runs out rather than a spinner, and a "back" that only means anything once
 * the hub has actually been away. The bug this holds shut is the second one -- the brain answers the
 * request and then waits a beat before it goes, so the link is still up when the tap finishes and a
 * naive "link came back" would clear the overlay before the hub had left. docs/restart.md, piece 4.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api')
  return { ...actual, doRestart: vi.fn(async (rung: string) => ({ rung, seconds: 34, how_long: 'about 30 seconds' })) }
})

import { doRestart } from '../src/api'
import { restartHub, restartLink, store } from '../src/store'

beforeEach(() => {
  vi.useFakeTimers()
  store.restarting = null
  store.toast = null
  vi.mocked(doRestart).mockClear()
})

describe('asking for a restart', () => {
  it('counts down from what the hub said it takes, not from a guess', async () => {
    await restartHub('hub')
    expect(store.restarting?.left).toBe(34)
    vi.advanceTimersByTime(4000)
    expect(store.restarting?.left).toBe(30)
  })

  it('stops at nought rather than counting into the negative', async () => {
    await restartHub('hub')
    vi.advanceTimersByTime(60_000)
    expect(store.restarting?.left).toBe(0)     // the words change; the number does not go backwards
  })

  it('carries the rung, so the overlay can name what is restarting', async () => {
    await restartHub('machine', true)
    expect(store.restarting?.rung).toBe('machine')
    expect(doRestart).toHaveBeenCalledWith('machine', true)
  })

  it('keeps the question up when the hub refuses', async () => {
    vi.mocked(doRestart).mockRejectedValueOnce(new Error('The hub is installing an update.'))
    expect(await restartHub('hub')).toBe(false)
    expect(store.restarting).toBeNull()
    expect(store.toast?.text).toContain('installing an update')
  })

  it('has not come back until it has gone', async () => {
    /* The guard. Without it, the link event that is STILL UP a beat after the tap reads as the hub
       returning and takes the overlay away while the brain is on its way down. */
    await restartHub('hub')
    expect(restartLink(true)).toBe(false)          // still up; it has not been anywhere
    expect(store.restarting).not.toBeNull()
    expect(restartLink(false)).toBe(false)         // there it goes
    expect(restartLink(true)).toBe(true)           // ...and there it is
    expect(store.restarting).toBeNull()
  })

  it('says how long it was actually away, not how long it said it would be', async () => {
    await restartHub('hub')
    restartLink(false)
    vi.advanceTimersByTime(41_000)
    restartLink(true)
    expect(store.toast?.text).toBe('Back. That took 41 seconds.')
  })

  it('says nothing when no restart was asked for', () => {
    store.restarting = null
    expect(restartLink(false)).toBe(false)
    expect(restartLink(true)).toBe(false)
    expect(store.toast).toBeNull()
  })
})
