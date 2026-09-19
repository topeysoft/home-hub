// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A bridge that went in has to be acknowledged, or it never goes away.
 *
 * What made this a spec: a puck was set up successfully, "It's in." was read and Done was pressed,
 * and the sheet came back a minute later. Then again. Then again. Closing it only changed the
 * panel's own copy of the state; the brain still had the finished job and answered every poll with
 * it, so the sheet reopened for ever and Done did nothing the hub could hear.
 *
 * The same bug had already been found and fixed for a job that FAILED, and the fix was written as
 * `if (was === 'failed')` -- so success kept it. This asserts the thing that was actually wrong: the
 * dismissal reaches the brain, and the state it then reports is one that draws nothing.
 *
 * Routed rather than driven through the mock's own bridge state, because the suite runs fully
 * parallel against one mock: pinning a bridge globally would drop a full-screen sheet over whatever
 * the other specs were clicking on.
 */
import { expect, test } from '@playwright/test'

const IN = /It.s in\./

test('a finished bridge is acknowledged, so it does not come back', async ({ page }) => {
  let told = 0
  let state: 'ready' | 'none' = 'ready'
  const body = () => state === 'ready'
    ? { state: 'ready', how: 'cable', switches: 5, unplaced: 3, bridges: 1, waiting: 0 }
    : { state: 'none', bridges: 1, waiting: 0 }

  // Registered first, so the more specific route below is matched before it.
  await page.route('**/bridge', route => route.fulfill({ json: body() }))
  await page.route('**/bridge/dismiss', route => {
    told++
    state = 'none'          // the brain, behaving like the brain: told once, it stops saying it
    return route.fulfill({ json: body() })
  })

  await page.goto('/?at=13:00', { waitUntil: 'networkidle' })
  const sheet = page.getByRole('dialog', { name: IN })
  await expect(sheet).toBeVisible()

  await page.getByRole('button', { name: 'Done' }).click()
  await expect(sheet).toBeHidden()
  expect(told, 'pressing Done has to reach the brain, or the next poll brings the sheet back').toBe(1)

  // The proof, and the thing a person actually experienced: come back to the panel and it is gone.
  await page.goto('/?at=13:00', { waitUntil: 'networkidle' })
  await expect(page.getByRole('dialog', { name: IN })).toBeHidden()
})
