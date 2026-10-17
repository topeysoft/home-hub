// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The wall's own keyboard, C in design/keyboard/, used with a finger in the built panel.

   The unit tests pin the rules. These pin what only the browser shows: that a tap on a field brings
   the keyboard up without taking the focus away from the field, that the keys type into it, that the
   command box is finished in the house's words, that the page moves the field above the keyboard
   rather than under it, and that none of it happens on a screen that is not the wall. */
import { expect, test, type Page } from '@playwright/test'

// The wall's own screen, used with a finger: the touch project's tablet is portrait, where the command box is not
// near the bottom and nothing would ever need to move.
test.use({ viewport: { width: 1440, height: 900 }, hasTouch: true })

const key = (page: Page, c: string) => page.locator('.wallkey', { hasText: new RegExp(`^${c}$`) }).first()
async function typeOn(page: Page, text: string) {
  for (const c of text) await (c === ' ' ? page.locator('.wallkey.space') : key(page, c)).tap()
}

test('a phone or tablet keeps its own keyboard: nothing is drawn without ?wall=1', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[data-keys=command]').tap()
  await expect(page.locator('.wallkeys')).toHaveCount(0)
})

test('the command box gets letters, and the house finishes the sentence', async ({ page }) => {
  await page.goto('/?wall=1')
  const box = page.locator('input[data-keys=command]')
  await box.tap()
  await expect(page.locator('.wallkeys')).toHaveAttribute('data-shape', 'command')
  await expect(page.locator('.wallkey.go')).toHaveText('Go')
  await typeOn(page, 'kitchen li')
  await expect(box).toHaveValue('kitchen li')
  await expect(box).toBeFocused()
  await expect(page.locator('.wallkeys-chip').first()).toHaveText('kitchen lights off')
  await page.locator('.wallkeys-chip').first().tap()
  await expect(box).toHaveValue('kitchen lights off')
})

test('the page moves the field above the keyboard, and back when the keyboard goes', async ({ page }) => {
  await page.goto('/?wall=1')
  const box = page.locator('input[data-keys=command]')
  await box.tap()
  await typeOn(page, 'kitchen')
  await expect(page.locator('.wallkeys-chip').first()).toBeVisible()
  await expect.poll(async () => {
    const [b, k] = await Promise.all([box.boundingBox(), page.locator('.wallkeys').boundingBox()])
    return b && k ? Math.round(k.y - (b.y + b.height)) : -1
  }).toBeGreaterThanOrEqual(0)
  await page.locator('.say-hint').first().tap()
  await expect(page.locator('.wallkeys')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--keys-lift').trim())).toBe('0px')
})

test('a passcode gets a keypad, with Continue where the lock screen puts it, and shows as dots', async ({ page }) => {
  await page.goto('/?wall=1&setup=1')
  await page.getByText('Get started').tap()
  const pin = page.locator('input.code-input').first()
  await pin.tap()
  await expect(page.locator('.wallkeys')).toHaveAttribute('data-shape', 'pad')
  await expect(page.locator('.wallkey.go')).toHaveText('Continue')
  await expect(page.locator('.wallkeys .wallkey')).toHaveCount(12)
  await typeOn(page, '2468')
  await expect(pin).toHaveValue('2468')
  // somebody may be standing behind the wall: the code is typed as dots
  expect(await pin.evaluate((el) => getComputedStyle(el).getPropertyValue('-webkit-text-security'))).toBe('disc')
  await page.locator('.wallkey[aria-label=Delete]').tap()
  await expect(pin).toHaveValue('246')
})
