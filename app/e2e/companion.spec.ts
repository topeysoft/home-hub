// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A wall screen joining a house whose hub is somewhere else (design/companion/, C, chosen 7 October 2026).

   The wall unit and the tablet open the panel with ?screen=1. Not in the house yet, the screen says whose house
   it found and asks for the passcode -- no name, because a screen is nobody's. In, it asks which room it is in,
   and from then on it opens on that room. ?join=1 holds the join screen up against the mock, which has no code. */
import { expect, test } from '@playwright/test'

test('a screen joins with the passcode, says which room it is in, and opens on that room from then on', async ({ page }) => {
  await page.route('**/phones/code', route => route.fulfill({ json: { ok: true, phone: { id: 's1', name: 'A screen', kind: 'screen', how: 'code', me: true } } }))
  await page.goto('/?screen=1&join=1&at=19:40', { waitUntil: 'networkidle' })

  await expect(page.locator('.join h1')).toHaveText('This screen is for Maple Court.')
  await expect(page.locator('.join .field-label')).toHaveCount(0)   // no "Your name"
  await expect(page.getByRole('button', { name: 'Ask from another screen' })).toBeVisible()
  await page.getByLabel('The passcode').fill('4821')
  await page.getByRole('button', { name: 'Continue' }).click()

  const step = page.locator('.screen-room')
  await expect(step.locator('h1')).toHaveText('Which room is this screen in?')
  // the house's name as the hub keeps it (the mock's /phones/me and /setup/status disagree; a hub reads one setting for both)
  const home = (await (await page.request.get('/setup/status')).json()).home
  await expect(step.locator('.screen-trail')).toContainText(home)
  await expect(step.getByRole('button', { name: 'Pick a room' })).toBeDisabled()
  await expect(step.locator('.screen-room-tile.new')).toContainText('Somewhere new')
  await step.locator('.screen-room-tile', { hasText: 'Kitchen' }).click()
  await expect(step.locator('.screen-room-tile.on')).toContainText('Kitchen')

  const placed = page.waitForRequest(r => r.url().endsWith('/phones/me/room') && r.method() === 'POST')
  await step.getByRole('button', { name: 'Open on the kitchen' }).click()
  expect((await placed).postDataJSON()).toEqual({ room: 'kitchen' })
  await expect(page.locator('.screen-room')).toHaveCount(0)
  await expect(page.locator('h1.display', { hasText: 'Kitchen' })).toBeVisible()

  // A restart opens the panel without ?screen=1; it is still a screen, and still in the kitchen.
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.screen-room')).toHaveCount(0)
  await expect(page.locator('h1.display', { hasText: 'Kitchen' })).toBeVisible()
})

test('a phone is never asked which room it is in', async ({ page }) => {
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.screen-room')).toHaveCount(0)
})

test('a resting screen wakes to its own room, not to Home', async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem('screen', '1'); localStorage.setItem('screen-room', 'kitchen') })
  await page.goto('/?rest=1&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.shell')).toHaveClass(/resting/)
  await page.mouse.click(700, 400)
  await expect(page.locator('.shell')).not.toHaveClass(/resting/)
  await expect(page.locator('h1.display', { hasText: 'Kitchen' })).toBeVisible()
})
