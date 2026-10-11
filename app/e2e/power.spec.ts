// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The house's power (design/energy/, B with C's sun): nothing on Home on an ordinary afternoon; one line in the
   band when it changes what somebody would do; and the pane that line opens. The mock's ?power= scenarios are
   the boards' numbers (mock/power.mjs). */
import { expect, test, type Page } from '@playwright/test'

const home = (page: Page, power: string) => page.goto(`/?layout=wall&nav=top&at=14:47&power=${power}`, { waitUntil: 'networkidle' })

test('an ordinary afternoon says nothing about power on Home, and the sun is warmer', async ({ page }) => {
  await home(page, 'afternoon')
  await expect(page.locator('.nudge', { hasText: /power|Sun to spare/i })).toHaveCount(0)
  await expect(page.locator('.wx-warm').first()).toBeAttached()
})

test('a house without a gateway draws the sun as the weather alone does', async ({ page }) => {
  await page.goto('/?layout=wall&nav=top&at=14:47', { waitUntil: 'networkidle' })
  await expect(page.locator('.wx-warm')).toHaveCount(0)
})

test('sun to spare is news in the band, and opens the pane', async ({ page }) => {
  await home(page, 'spare')
  const line = page.locator('.nudge', { hasText: 'Sun to spare' })
  await expect(line.locator('.nudge-sub')).toHaveText('The battery is full: a good time for the dryer or the car')
  await line.click()
  const pane = page.getByRole('dialog', { name: 'Power' })
  await expect(pane.locator('.opened-name')).toHaveText('Power')
  await expect(pane.locator('.power-big')).toContainText('5.1 kW')
})

test('the power out is a line of its own, first, and the pane says how long the battery lasts', async ({ page }) => {
  await home(page, 'out')
  const line = page.locator('.nudges > .nudge.power-out')
  await expect(line.locator('.nudge-title')).toHaveText('The power is out — the battery has the house')
  await expect(line.locator('.nudge-sub')).toHaveText('84%, about 14 hours as things are')
  await line.click()
  const pane = page.getByRole('dialog', { name: 'Power' })
  await expect(pane.locator('.pane-why')).toHaveText('The power is out. The battery has the house, and should last about 14 hours as things are.')
  await expect(pane.locator('.power-grid small')).toHaveText('Out')
})

test('This house has a door to it, saying how things stand', async ({ page }) => {
  await page.goto('/?layout=wall&nav=top&at=14:47&power=afternoon&sheet=house', { waitUntil: 'networkidle' })
  const door = page.locator('.door', { hasText: 'Solar and battery' })
  await expect(door.locator('.door-hint')).toHaveText('5.8 kW from the sun · battery 84%')
  await door.click()
  await expect(page.getByRole('dialog', { name: 'Power' })).toBeVisible()
})
