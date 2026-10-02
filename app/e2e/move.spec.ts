// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Moving a phone to the house's own name, pinned to design/away/ as chosen on 1 October (C): the band line on a
 * phone that has not moved (NamedC-home), the page it opens (NamedC-move), the Home only | Anywhere choice on
 * People (NamedC, in the words of design/words-people/ AnywhereC), and the away screen that waits and opens by itself (NamedC-out). They measure where things are and
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
    const line = page.locator('.nudge', { hasText: 'A new link for the house' })
    await expect(line).toHaveCount(1)
    await expect(line).toContainText('Switch this phone to main-palace.elyir.app')
    await line.click()
    const move = page.locator('main.move')
    await expect(move.locator('h1')).toHaveText('A new link for the house.')
    await expect(move.locator('.setup-lede')).toContainText('main-palace.elyir.app')
    await expect(move.locator('.move-steps li')).toHaveCount(3)
    await expect(move.locator('.move-steps li').nth(1)).toContainText('Add it to your Home Screen')
    // Nothing of the house shows under the page, and Not now is beside the button.
    await expect(page.locator('.topbar, .tabs')).toHaveCount(0)
    const [go, not] = [(await move.getByRole('button', { name: 'Switch this phone' }).boundingBox())!, (await move.getByRole('button', { name: 'Not now' }).boundingBox())!]
    expect(Math.abs(go.y - not.y)).toBeLessThan(4)
    await move.getByRole('button', { name: 'Not now' }).click()
    await expect(page.locator('main.move')).toHaveCount(0)
  })

  test('a phone that has moved, and the wall, get no line', async ({ page }) => {
    await withAddress(page, { ...ME, phone: { ...ME.phone, moved: true } })
    await page.goto('/')
    await expect(page.locator('.nudge').first()).toBeVisible()            // the band is up, so an absence means something
    await expect(page.locator('.nudge', { hasText: 'A new link for the house' })).toHaveCount(0)
  })

  test('People on a phone puts the two answers under the name, with Remove still on the first line', async ({ page }) => {
    await withAddress(page)
    await page.route('**/status', async r => { const res = await r.fetch(); const j = await res.json(); await r.fulfill({ json: { ...j, locked: true } }) })
    await page.goto('/?sheet=people')
    const row = page.locator('.phones li').filter({ has: page.getByRole('radiogroup') }).first()
    const [name, pick, rm] = [(await row.locator('.phones-name').boundingBox())!, (await row.getByRole('radiogroup').boundingBox())!, (await row.getByRole('button', { name: 'Remove' }).boundingBox())!]
    expect(pick.y).toBeGreaterThan(name.y + name.height)                // its own line, under the name
    expect(Math.abs(pick.x - name.x)).toBeLessThan(2)                     // and lined up with it
    expect(rm.y + rm.height).toBeLessThan(pick.y + 1)                     // Remove stays on the first line
    expect(name.height).toBeLessThan(30)                                  // so the name is one line, not a word a line
  })

  test('away, a phone the house knows waits and is told it opens by itself', async ({ page }) => {
    await page.goto('/?away=1')
    await expect(page.locator('main.away h1')).toHaveText('Set to Home only.')
    await expect(page.locator('main.away')).toContainText('This phone works on your home Wi‑Fi. Someone with the passcode can set it to Anywhere, in People.')
    await expect(page.locator('main.away .setup-status')).toHaveText(/This opens by itself as soon as they do\./)
  })
})

test.describe('on the wall', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('People offers Home only or Anywhere on each phone, says Home only for the wall, and says where the house is', async ({ page }) => {
    await withAddress(page, { ...ME, phone: { ...ME.phone, id: 'w', name: 'This wall', kind: 'wall', how: 'setup' } })
    await page.route('**/status', async r => { const res = await r.fetch(); const j = await res.json(); await r.fulfill({ json: { ...j, locked: true } }) })
    await page.goto('/?sheet=people')
    const rows = page.locator('.phones li').filter({ has: page.locator('.phones-icon') })
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(0)).toContainText('Wall screen')               // a house set up before the rename still reads plainly
    await expect(rows.nth(0).locator('.phones-where')).toHaveText('Home only')
    await expect(rows.nth(0).getByRole('radio')).toHaveCount(0)            // the wall never leaves, so there is nothing to pick
    for (const i of [1, 2]) {
      const pick = rows.nth(i).getByRole('radiogroup')
      await expect(pick.getByRole('radio')).toHaveText(['Home only', 'Anywhere'])
      await expect(pick.getByRole('radio', { name: 'Home only' })).toHaveAttribute('aria-checked', 'true')
      const [sw, rm] = [(await pick.boundingBox())!, (await rows.nth(i).getByRole('button', { name: 'Remove' }).boundingBox())!]
      expect(sw.x + sw.width).toBeLessThan(rm.x)          // the choice sits before Remove, on the same line
      expect(Math.abs((sw.y + sw.height / 2) - (rm.y + rm.height / 2))).toBeLessThan(6)
    }
    await expect(page.locator('.hub-rows')).toContainText('at main-palace.elyir.app')
    await expect(page.locator('.hub-rows')).not.toContainText('From outside')
    const pick = rows.nth(1).getByRole('radiogroup')
    await pick.getByRole('radio', { name: 'Anywhere' }).click()
    await expect(pick.getByRole('radio', { name: 'Anywhere' })).toHaveAttribute('aria-checked', 'true')
  })
})
