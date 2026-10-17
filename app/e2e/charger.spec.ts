// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A car charger (design/charger/, A with C's line): a card in its room that leads it while the car
   charges, and a line in Home's band. The mock's charger is plugged in and not charging, so the house is
   stubbed to charge it rather than started with a knob. */
import { expect, test, type Page } from '@playwright/test'

async function charging(page: Page) {
  await page.route('**/home', async (route) => {
    const res = await route.fetch(), home = await res.json()
    for (const r of home.rooms) for (const d of r.devices) if (d.capability === 'charger') Object.assign(d, { state: 'charging', attrs: { power: 7.2 } })
    route.fulfill({ json: home })
  })
}

test('charging, the charger leads its room as a half, in words and with no switch', async ({ page }) => {
  await charging(page)
  await page.goto('/?room=garage&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  const card = page.locator('.tile.plain.charger')
  await expect(card).toHaveAttribute('data-size', 'half')
  await expect(card).toHaveClass(/\bon\b/)
  await expect(card).toBeDisabled()
  await expect(card.locator('.tile-state')).toHaveText('Charging · 7.2 kW')
  await expect(page.locator('.room-head .lede')).toContainText('Charging the car')
  const first = await page.locator('.tiles > *').first().getAttribute('class')
  expect(first).toContain('charger')
})

test('plugged in and not charging, it is a third and says so', async ({ page }) => {
  await page.goto('/?room=garage&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  const card = page.locator('.tile.plain.charger')
  await expect(card).toHaveAttribute('data-size', 'third')
  await expect(card.locator('.tile-state')).toHaveText('Plugged in')
})

test("Home's band says the car is charging, with the power and the room", async ({ page }) => {
  await charging(page)
  await page.goto('/?layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  const chip = page.locator('.nudge.charging')
  await expect(chip).toHaveCount(1)
  await expect(chip.locator('.nudge-title')).toHaveText('The car is charging')
  await expect(chip.locator('.nudge-sub')).toHaveText('7.2 kW · Garage')
})
