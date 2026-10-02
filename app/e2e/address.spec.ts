// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The house's own address, pinned to the board the household chose on 1 October (design/address/,
 * OfferPlain and Named). The optional last step of setup says the house is complete without it, puts
 * the price in the open beside what stopping does, offers three free names when one is taken, and sends
 * the paying to a phone -- and This hub then carries a row for it between Network and Language. These
 * measure where things are, so they fail on purpose if the arrangement drifts from the board.
 *
 * The mock brain offers an address unless OUTSIDE=closed, and `palace` is another house's there.
 */
import { expect, test } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

test('the step says the house is complete, puts the price beside what stopping does, and fits the wall', async ({ page }) => {
  await page.goto('/?setup=1&page=address')
  const step = page.locator('.address-step')
  await expect(step.locator('.setup-step')).toHaveText('Optional')
  await expect(step.locator('h1')).toHaveText('Use it anywhere?')
  await expect(step.locator('.setup-lede')).toContainText('The house already works fully at home.')
  await expect(step.locator('.setup-lede')).toContainText('through a service we run')
  await expect(step.locator('.address-name input')).toHaveValue('temi')
  await expect(step.locator('.address-said')).toHaveText('temi.elyir.app is free')
  await expect(step.locator('.address-amount')).toHaveText('$3')
  await expect(step.locator('.address-cost')).toContainText('a month · stop any time')
  await expect(step.locator('.address-stop')).toContainText('phones go back to Home only')
  // Paying is on a phone, and Not now is offered beside it, the same size of thing.
  const take = step.getByRole('button', { name: 'Continue on your phone' }), not = step.getByRole('button', { name: 'Not now' })
  await expect(take).toBeEnabled()
  const [t, n] = [(await take.boundingBox())!, (await not.boundingBox())!]
  expect(Math.abs(t.y - n.y)).toBeLessThan(4)                 // one row
  // The verdict sits beside the field, not under it.
  const [field, said] = [(await step.locator('.address-name').boundingBox())!, (await step.locator('.address-said').boundingBox())!]
  expect(said.x).toBeGreaterThan(field.x + field.width)
  expect(Math.abs((said.y + said.height / 2) - (field.y + field.height / 2))).toBeLessThan(12)
  // One screen on a wall: nothing of the step below the fold.
  const foot = (await step.locator('.setup-foot').boundingBox())!
  expect(foot.y + foot.height).toBeLessThanOrEqual(900)
})

test('a name another house has is one line and three free ones, and the button waits for a free one', async ({ page }) => {
  await page.goto('/?setup=1&page=address')
  const step = page.locator('.address-step')
  await step.locator('.address-name input').fill('palace')
  await expect(step.locator('.address-said')).toHaveText('palace.elyir.app is another house’s')
  await expect(step.locator('.address-said')).toHaveClass(/no/)
  await expect(step.locator('.address-picks .chip-btn')).toHaveCount(3)
  await expect(step.getByRole('button', { name: 'Continue on your phone' })).toBeDisabled()
  await step.locator('.address-picks .chip-btn').first().click()
  await expect(step.locator('.address-name input')).toHaveValue('palace-house')
  await expect(step.locator('.address-said')).toHaveText('palace-house.elyir.app is free')
})

test('taking it sends the paying to a phone, and Not now is still there', async ({ page }) => {
  await page.goto('/?setup=1&page=address')
  const step = page.locator('.address-step')
  await expect(step.locator('.address-said')).toHaveText('temi.elyir.app is free')
  await step.getByRole('button', { name: 'Continue on your phone' }).click()
  await expect(page.locator('.address-step h1')).toHaveText('Finish on your phone.')
  await expect(page.locator('.address-step .phone-qr img')).toBeVisible()
  await expect(page.locator('.address-step')).toContainText('temi.elyir.app')
  await expect(page.locator('.address-step').getByRole('button', { name: 'Not now' })).toBeVisible()
})

test('This hub carries the address between Network and Language once the house has one', async ({ page }) => {
  await page.route('**/address', r => r.request().method() === 'GET'
    ? r.fulfill({ json: { offer: { open: true, price: '$3 a month', pay: null }, guess: 'temi', house: 'temi', address: 'temi.elyir.app', want: 'on', on: true, carried: true, entitled_until: Date.UTC(2027, 9, 1) / 1000 } })
    : r.continue())
  await page.goto('/?sheet=hub')
  const keys = page.locator('.hub-rows > li > .hub-k')
  await expect(keys.filter({ hasText: 'Web address' })).toHaveCount(1)
  const order = await keys.allTextContents()
  expect(order.indexOf('Web address')).toBe(order.indexOf('Network') + 1)
  expect(order.indexOf('Language')).toBe(order.indexOf('Web address') + 1)
  const row = page.locator('.hub-rows > li').filter({ has: page.locator('.hub-k', { hasText: 'Web address' }) })
  await expect(row).toContainText('temi.elyir.app · on')
  await expect(row).toContainText('Paid up until October 1, 2027.')
  await expect(row.getByRole('button', { name: 'Turn off' })).toBeVisible()
})
