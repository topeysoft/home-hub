// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What this house has: the one door, on the glass. design/forget/ThingsDoor.dc.html.
 *
 * The page is nearly all template, so this is where its arrangement is held. Three things have to
 * be true, and each of them is a decision that was made before the code:
 *
 *   - It is grouped by WHAT BROUGHT A THING, and a thing an account brought has no way out of its
 *     own -- it says so on the row, with the door to the account on the group above it.
 *   - Every word on it comes from the brain. The panel draws the acts and invents none of them, so
 *     the question a person reads before an act with no undo is written in one place.
 *   - Nothing goes without being asked, and the asking names the thing.
 */
import { expect, test } from '@playwright/test'

const DOOR = '/?sheet=things&at=19:40'
const page_ = (page: import('@playwright/test').Page) => page.locator('.page-things')

test('everything is under what brought it, and the group carries the bigger hammer', async ({ page }) => {
  await page.goto(DOOR, { waitUntil: 'networkidle' })
  const ring = page_(page).locator('.things', { hasText: 'Ring · signed in' })
  await expect(ring).toBeVisible()
  // the row itself offers nothing: what brought it is what decides, and it is named
  await expect(ring.locator('.things-why').first()).toHaveText('Goes with Ring')
  await expect(ring.locator('.things-do .button')).toHaveCount(0)
  // ...and the way out of it is the account, said where the reason for it is visible
  await expect(ring.locator('.things-a')).toContainText('Remove Ring')
})

test('a thing set up here goes on its own, and is asked about by name first', async ({ page }) => {
  await page.goto(DOOR, { waitUntil: 'networkidle' })
  const row = page_(page).locator('.things-rows li', { hasText: 'Backyard cam' }).first()
  await expect(row.locator('.button')).toHaveText('Take it out')
  await expect(row.locator('.things-ask')).toHaveCount(0)   // nothing is armed until it is touched
  await row.locator('.button').click()
  const ask = row.locator('.things-ask')
  await expect(ask).toContainText('Take Backyard cam out of the house?')
  await expect(ask.locator('.button.warn')).toHaveText('Yes, take Backyard cam out')
  await expect(ask.locator('.button.ghost')).toHaveText('Keep it')
})

test('the sentence a person reads before it is readable, which is not a matter of taste here', async ({ page }) => {
  /* A plain .button is near-white with dark ink on it. Taking only its text to the danger color put
     pale pink on white and made the one irreversible button the faintest thing on the screen. */
  await page.goto(DOOR, { waitUntil: 'networkidle' })
  const row = page_(page).locator('.things-rows li', { hasText: 'Backyard cam' }).first()
  await row.locator('.button').click()
  const yes = row.locator('.things-ask .button.warn')
  const paint = await yes.evaluate((el) => {
    const cs = getComputedStyle(el)
    return { bg: cs.backgroundColor, fg: cs.color }
  })
  expect(paint.bg, 'the one button with no undo has no field of its own').not.toBe('rgba(0, 0, 0, 0)')
  expect(paint.fg).not.toBe(paint.bg)
})

test('a room a thing is in is said on its row, because that is how somebody finds it', async ({ page }) => {
  await page.goto(DOOR, { waitUntil: 'networkidle' })
  const row = page_(page).locator('.things-rows li', { hasText: 'Backyard cam' }).first()
  await expect(row.locator('.things-where')).toHaveText('Backyard')
})

test('the door into it says how much is behind it, in things rather than in entries', async ({ page }) => {
  await page.goto('/?sheet=house&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.door', { hasText: 'What this house has' }))
    .toContainText(/\d+ things, and what brought each of them/)
})

test('nothing on the list is glass, which is what made it unusable to scroll', async ({ page }) => {
  /* REPORTED 22 SEPTEMBER: scrolling this page dropped rows and then took the whole view down.
     Nothing was wrong with the DOM -- a per-frame trace found all 37 rows present and none of them
     zero height -- because it was never a layout problem. `.button.ghost` carries a backdrop-filter,
     which is a live compositing layer that re-samples what is behind it on every frame; every other
     page under This house has four to six, and a row button on a real house's worth of rows made
     thirty-four, inside a scroller inside a rounded overflow:hidden panel.

     Headless Chromium does not composite, so it renders this perfectly and can never catch the bug.
     Counting the glass is the thing it CAN do, so that is what is pinned here. */
  await page.goto(DOOR, { waitUntil: 'networkidle' })
  const frosted = await page_(page).evaluate((el) =>
    [...el.querySelectorAll('*')].filter(n => {
      const v = getComputedStyle(n).backdropFilter
      return !!v && v !== 'none'
    }).map(n => n.className))
  expect(frosted, 'a row on a long list is not glass over the sky').toEqual([])
})
