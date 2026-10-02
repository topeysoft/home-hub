// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* First run's words, pinned to the board the household chose on 2 October (design/words-setup/, B: say less).
 * One sentence a screen; the machinery stays on This hub and shows here only when it needs the person; the
 * last screen keeps one tip, and every place it names is a place that exists. These fail on purpose if a
 * sentence grows back, or if a screen starts naming a page the panel no longer has.
 */
import { expect, test } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

test('welcome says one thing, and the passcode says what it is for, phones included', async ({ page }) => {
  await page.goto('/?setup=1&page=welcome')
  await expect(page.locator('.setup-lede')).toHaveText('Run the whole house from this screen. Setting it up takes a few minutes.')
  await page.goto('/?setup=1&page=code')
  await expect(page.locator('h1')).toHaveText('Choose a passcode.')
  await expect(page.locator('.setup-lede')).toContainText('add phones or devices')
  await expect(page.locator('.field-label')).toHaveText(['Passcode, 4 to 8 digits', 'Type it again'])
})

test('signing in to a hub set up by hand never names the engine', async ({ page }) => {
  await page.goto('/?setup=1&page=login')
  await expect(page.locator('.setup-page')).not.toContainText('Home Assistant')
  await expect(page.getByRole('link', { name: 'Reset it in Advanced' })).toBeVisible()
})

test('what is in the house shows the machinery only where it needs the person', async ({ page }) => {
  await page.goto('/?setup=1&page=devices')
  await expect(page.locator('.setup-page')).not.toContainText('Behind the scenes')
  const rows = page.locator('.setup-behind .drivers li')
  await expect(rows).toHaveCount(1)                                   // the mock's Ring sign-in, and none of its radios
  await expect(rows).toContainText('Ring needs you to sign in')
  await expect(rows.getByRole('link', { name: 'Sign in' })).toBeVisible()
})

test('the last screen keeps one tip, and names only places that exist', async ({ page }) => {
  await page.goto('/?setup=1&page=done')
  await expect(page.locator('.tips li')).toHaveCount(1)
  await expect(page.locator('.tips li')).toContainText('Tell the house…')
  for (const gone of ['Found nearby', 'on the Home screen', 'top of Home', 'Open Home']) await expect(page.locator('.setup-page')).not.toContainText(gone)
  await expect(page.getByRole('button', { name: 'Start using the house' })).toBeInViewport()
})

test('a sign-in that needs doing comes before the way on, and is never under it', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })              // the kiosk wall, where this step docks
  await page.goto('/?setup=1&page=devices')
  const row = page.locator('.setup-behind .drivers li').first(), go = page.locator('.setup-actions .button.big')
  await row.scrollIntoViewIfNeeded()
  const [r, g] = [(await row.boundingBox())!, (await go.boundingBox())!]
  expect(r.y + r.height).toBeLessThan(g.y)
  await expect(row).toBeInViewport({ ratio: 1 })
})
