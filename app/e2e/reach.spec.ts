// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A screen that can't reach the hub says so (design/out-of-reach/, C, decided 9 October 2026).
 *
 * The evening it is drawn from: the kitchen screen's live connection stayed up while every new request
 * failed, so it looked current, said Connected, and flipped each tapped card off and back on with the
 * light blamed. Here the same thing is staged -- fresh requests refused, the stream left alone -- and the
 * screen has to say so without the light taking the blame, and without a card flipping under the finger.
 */
import { expect, test, type Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

async function kitchenScreen(page: Page) {
  await page.addInitScript(() => { localStorage.setItem('screen', '1'); localStorage.setItem('screen-room', 'kitchen') })
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('h1.display', { hasText: 'Kitchen' })).toBeVisible()
}

/** Every new request refused, the way a screen that has lost the hub's name sees it. The stream stays up. */
const cutOff = (page: Page) => Promise.all([
  page.route('**/alive', r => r.abort('failed')),
  page.route('**/devices/**', r => r.request().method() === 'POST' ? r.abort('failed') : r.fallback()),
])
const reconnect = (page: Page) => Promise.all([page.unroute('**/alive'), page.unroute('**/devices/**')])

const lights = (page: Page) => page.locator('.tile.light', { hasText: 'Lights' }).first()
const coffee = (page: Page) => page.locator('.tile.plain', { hasText: 'Coffee maker' }).first()
const band = (page: Page) => page.locator('.reach-band')

test('a tap that never reached the hub says so on the card, and the screen says why along its foot', async ({ page }) => {
  await kitchenScreen(page)
  await expect(page.locator('.link.up').first()).toHaveText('Connected')
  await cutOff(page)

  await lights(page).click()
  await expect(lights(page)).toHaveClass(/unreached/)
  await expect(lights(page).locator('.tile-said')).toHaveText('Still on')
  await expect(lights(page).locator('.tile-why')).toHaveText('Changes can’t get through. Use the switch.')
  await expect(band(page)).toContainText('Changes made here aren’t reaching the hub')
  await expect(band(page)).toContainText('The switches on the wall still work.')
  await expect(page.locator('.link.out').first()).toHaveText('Can’t reach the hub')
  await expect(page.locator('.toast.error')).toHaveCount(0)
  await expect(page.locator('main.stage')).not.toHaveClass(/hushed/)
})

test('once it knows, a tap guesses nothing: the card never shows a state it does not have', async ({ page }) => {
  await kitchenScreen(page)
  await cutOff(page)
  await lights(page).click()
  await expect(band(page)).toBeVisible()

  // every frame of the second tap, read in the page: a screenshot is slower than the flip it is looking for
  await page.evaluate(() => {
    const seen: string[] = []; (window as any).__seen = seen
    const tile = [...document.querySelectorAll('.tile.plain')].find(t => t.textContent?.includes('Coffee maker'))!
    const tick = () => { seen.push(tile.querySelector('.tile-state')?.textContent?.trim() ?? ''); if (seen.length < 120) requestAnimationFrame(tick) }
    requestAnimationFrame(tick)
  })
  await coffee(page).click()
  await page.waitForFunction(() => (window as any).__seen.length >= 120)
  const seen: string[] = await page.evaluate(() => (window as any).__seen)
  expect(new Set(seen.map(s => s.replace(/Changes.*/, '')))).toEqual(new Set(['Off', 'Still off']))
  await expect(coffee(page).locator('.tile-said')).toHaveText('Still off')
})

test('Try now that gets through takes the band, the card sentences and the corner back', async ({ page }) => {
  await kitchenScreen(page)
  await cutOff(page)
  await lights(page).click()
  await expect(band(page)).toBeVisible()

  await reconnect(page)
  await band(page).getByRole('button', { name: 'Try now' }).click()
  await expect(band(page)).toHaveCount(0)
  await expect(lights(page)).not.toHaveClass(/unreached/)
  await expect(page.locator('.link.up').first()).toHaveText('Connected')
})

test('when nothing comes in either, the room is hushed and the band says when it last heard', async ({ page }) => {
  await page.routeWebSocket('**/stream', ws => { ws.close() })
  await kitchenScreen(page).catch(() => {})
  await expect(band(page)).toContainText('This screen can’t reach the hub', { timeout: 15_000 })
  await expect(band(page)).toContainText('Last heard from it at')
  await expect(page.locator('main.stage')).toHaveClass(/hushed/)
  await expect(page.locator('.banner')).toHaveCount(0)
})
