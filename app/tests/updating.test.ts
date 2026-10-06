// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The several minutes an update takes.
 *
 * The thing this holds shut is the difference between an update and a restart: for nearly all of an
 * update the brain is UP -- the code, the signature and the download all happen with it running --
 * so the house works and the panel must not throw a blackout screen over a hub that is merely
 * fetching something. Only the last stretch is dark, and only that stretch gets counted down.
 * docs/updates.md, piece 6.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api')
  return { ...actual, requestUpdate: vi.fn(async () => ({ dark_seconds: 42, seconds: 300, requested: true })) }
})

import { requestUpdate } from '../src/api'
import { beginUpdate, endUpdate, installUpdate, plainly, updateLink, store } from '../src/store'

beforeEach(() => {
  vi.useFakeTimers()
  endUpdate()
  store.toast = null
  store.status = null as any
  vi.mocked(requestUpdate).mockClear()
})

describe('asking for an update', () => {
  it('counts the dark stretch the hub measured, not the whole wait', async () => {
    expect(await installUpdate()).toBe(true)
    expect(store.updating?.dark).toBe(42)
  })

  it('does not start counting down while the house still works', async () => {
    /* The whole point. The number is for the stretch the brain is away; running it during the
       download would have it reach nought minutes before anything had even restarted. */
    await installUpdate()
    vi.advanceTimersByTime(20_000)
    expect(store.updating?.left).toBe(42)
    expect(store.updating?.lost).toBe(false)
  })

  it('starts counting once the brain has actually gone', async () => {
    await installUpdate()
    updateLink(false)
    vi.advanceTimersByTime(10_000)
    expect(store.updating?.left).toBe(32)
  })

  it('stops at nought rather than counting into the negative', async () => {
    await installUpdate()
    updateLink(false)
    vi.advanceTimersByTime(300_000)
    expect(store.updating?.left).toBe(0)      // the words change; the number does not go backwards
  })

  it('leaves nothing up when the hub refuses', async () => {
    vi.mocked(requestUpdate).mockRejectedValueOnce(new Error('That update has been paused by the people who make the hub.'))
    expect(await installUpdate()).toBe(false)
    expect(store.updating).toBeNull()
    expect(store.toast?.text).toContain('paused')
  })
})

describe('an update nobody on this screen asked for', () => {
  it('can be picked up mid-flight from what the hub is reporting', () => {
    /* The ordinary way an update happens is at twenty to three with nobody in front of the wall.
       The screen still has to be able to draw the wait. */
    beginUpdate(55)
    expect(store.updating?.dark).toBe(55)
    expect(store.updating?.lost).toBe(false)
  })

  it('does not restart its own clock every time the status comes round again', () => {
    beginUpdate(55)
    const at = store.updating!.at
    updateLink(false)
    vi.advanceTimersByTime(5000)
    beginUpdate(55)
    expect(store.updating!.at).toBe(at)
    expect(store.updating!.left).toBe(50)
  })

  it('falls back to a careful guess on a hub too old to have an opinion', () => {
    beginUpdate(undefined)
    expect(store.updating?.dark).toBe(60)
  })
})

describe('saying how long it took', () => {
  it('rounds the way the brain does, because the two quote the same figures at people', () => {
    expect(plainly(34)).toBe('about 30 seconds')
    expect(plainly(240)).toBe('about 4 minutes')
  })
})
