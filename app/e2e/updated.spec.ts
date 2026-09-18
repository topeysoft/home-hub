// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* After an update the hub comes back on a new build, and the page has to come with it: until it
 * reloads, the wall is last week's panel talking to this week's brain, and nothing on the glass says
 * so. What is under test is that the page reloads by itself when the hub answers with a different
 * version, and that the page after the reload still says what happened -- a toast does not survive
 * a reload on its own.
 *
 * The new version is spoken into the page's own stream by the test, as the hub would speak it when
 * it comes back: the mock does not restart, and the real one takes the link down for a minute, which
 * is exactly why the reload rides the version and not the link.
 */
import { expect, test } from '@playwright/test'

const WALL = '/?face=glass&layout=wall&nav=top&at=19:40'

test('the wall follows the hub onto the new build, and says so', async ({ page }) => {
  let speak: ((msg: string) => void) | undefined
  await page.routeWebSocket('**/stream', ws => { ws.connectToServer(); speak = m => ws.send(m) })
  await page.goto(WALL, { waitUntil: 'networkidle' })
  const status = await (await page.request.get('/setup/status')).json()
  expect(status.version, 'the mock has to say which build it is').toBe('v0.3.0')

  const before = await page.evaluate(() => performance.timeOrigin)
  const reloaded = page.waitForEvent('load')
  speak!(JSON.stringify({ type: 'status', status: { ...status, version: 'v0.3.1' } }))
  await reloaded
  const after = await page.evaluate(() => performance.timeOrigin)
  expect(after, 'the page did not reload').toBeGreaterThan(before)
  await expect(page.locator('.toast')).toHaveText(/Updated to v0\.3\.1\./)
  // ...and it is the house again, not a page stuck on a message
  await expect(page.locator('.offline')).toHaveCount(0)
})

test('the same build again is not an update', async ({ page }) => {
  let speak: ((msg: string) => void) | undefined
  await page.routeWebSocket('**/stream', ws => { ws.connectToServer(); speak = m => ws.send(m) })
  await page.goto(WALL, { waitUntil: 'networkidle' })
  const status = await (await page.request.get('/setup/status')).json()
  const before = await page.evaluate(() => performance.timeOrigin)
  speak!(JSON.stringify({ type: 'status', status }))
  await page.waitForTimeout(500)
  expect(await page.evaluate(() => performance.timeOrigin)).toBe(before)
  await expect(page.locator('.toast')).toHaveCount(0)
})
