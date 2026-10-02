// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Moving a phone to the house's own name, pinned to design/away/ as chosen on 1 October (C): the band line on a
 * phone that has not moved (NamedC-home), the page it opens (NamedC-move), the From outside switch on People
 * (NamedC), and the away screen that waits and opens by itself (NamedC-out). They measure where things are and
 * what they say, so they fail on purpose if the arrangement drifts from the boards.
 *
 * The suite's mock starts with no address, so each test answers /phones/me itself.
 */
import { expect, test, type Page } from '@playwright/test'

const ME = { locked: true, paired: true, home: 'Main Palace', away: false, lan: '192-168-86-53.main-palace.home.elyir.app', address: 'https://main-palace.elyir.app',
  phone: { id: 'p1', name: "Temi's iPhone", kind: 'phone', joined: 0, expires: null, remote: false, last_seen: null, how: 'code', me: true, moved: false } }

async function withAddress(page: Page, me: object = ME) {
  await page.route('**/phones/me', r => r.fulfill({ json: me }))
}

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('a phone that has not moved gets one line, and it opens the move', async ({ page }) => {
    await withAddress(page)
    await page.goto('/')
    const line = page.locator('.nudge', { hasText: 'The house has its own address' })
    await expect(line).toHaveCount(1)
    await expect(line).toContainText('Move this phone to main-palace.elyir.app, once')
    await line.click()
    const move = page.locator('main.move')
    await expect(move.locator('h1')).toHaveText('Move this phone.')
    await expect(move.locator('.setup-lede')).toContainText('main-palace.elyir.app')
    await expect(move.locator('.move-steps li')).toHaveCount(3)
    await expect(move.locator('.move-steps li').nth(1)).toContainText('Add it to your home screen')
    // Nothing of the house shows under the page, and Not now is beside the button.
    await expect(page.locator('.topbar, .tabs')).toHaveCount(0)
    const [go, not] = [(await move.getByRole('button', { name: 'Move this phone' }).boundingBox())!, (await move.getByRole('button', { name: 'Not now' }).boundingBox())!]
    expect(Math.abs(go.y - not.y)).toBeLessThan(4)
    await move.getByRole('button', { name: 'Not now' }).click()
    await expect(page.locator('main.move')).toHaveCount(0)
  })

  test('a phone that has moved, and the wall, get no line', async ({ page }) => {
    await withAddress(page, { ...ME, phone: { ...ME.phone, moved: true } })
    await page.goto('/')
    await expect(page.locator('.nudge').first()).toBeVisible()            // the band is up, so an absence means something
    await expect(page.locator('.nudge', { hasText: 'The house has its own address' })).toHaveCount(0)
  })

  test('away, a phone the house knows waits and is told it opens by itself', async ({ page }) => {
    await page.goto('/?away=1')
    await expect(page.locator('main.away h1')).toHaveText('Not from here, yet.')
    await expect(page.locator('main.away')).toContainText('This phone works at home. Someone at the wall can let it out.')
    await expect(page.locator('main.away .setup-status')).toHaveText(/It opens by itself when they do\./)
  })
})

test.describe('on the wall', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('People has From outside on each phone, never on the wall, and says where the house is', async ({ page }) => {
    await withAddress(page, { ...ME, phone: { ...ME.phone, id: 'w', name: 'This wall', kind: 'wall', how: 'setup' } })
    await page.route('**/status', async r => { const res = await r.fetch(); const j = await res.json(); await r.fulfill({ json: { ...j, locked: true } }) })
    await page.goto('/?sheet=people')
    const rows = page.locator('.phones li').filter({ has: page.locator('.phones-icon') })
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(0)).toContainText('stays home')
    // When each was last seen, so rows of the same name can be told apart (the note beside NamedC).
    await expect(rows.nth(0)).toContainText('seen just now · stays home')
    await expect(rows.nth(1)).toContainText('seen 1 hour ago')
    await expect(rows.nth(0).locator('.phones-outside')).toHaveCount(0)
    for (const i of [1, 2]) {
      await expect(rows.nth(i).locator('.phones-outside')).toContainText('From outside')
      const [sw, rm] = [(await rows.nth(i).locator('.toggle').boundingBox())!, (await rows.nth(i).getByRole('button', { name: 'Remove' }).boundingBox())!]
      expect(sw.x + sw.width).toBeLessThan(rm.x)          // the switch sits before Remove, on the same line
      expect(Math.abs((sw.y + sw.height / 2) - (rm.y + rm.height / 2))).toBeLessThan(6)
    }
    await expect(page.locator('.hub-rows')).toContainText('at main-palace.elyir.app')
    await rows.nth(1).locator('.toggle').click()
    await expect(rows.nth(1).locator('.toggle')).toHaveClass(/on/)
  })
})
