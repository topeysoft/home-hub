// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The band, and the row that no longer moves for it.

   The row is the whole of what Wall buys: 548 of the board's 900, paid for with the greeting, the
   house line and the next-up line. A house with something to attend to used to hand 35px of that
   back, which is the worst of both -- the row got shorter and the urgent thing was no louder for
   it. Everything else in this file follows from taking the band out of the flow, which is only
   possible because a phone at the door is a pane now and a fault list is a page, so nothing left in
   the band is taller than one line.

   Measured in the page rather than across two loads. A before-and-after needs two houses, and the
   thing that decides what is in the band -- whether the house is locked, what the health endpoint
   says -- can be pushed in by the live stream between them. Adding and removing chips in the DOM
   asks the same question of one layout. */
import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento').first()).toBeVisible()
  await page.waitForTimeout(1400)
})

test('the band sits between the bar and the row, and takes nothing from either', async ({ page }) => {
  const bar = (await page.locator('.topbar').boundingBox())!
  const band = (await page.locator('.nudges').boundingBox())!
  const row = (await page.locator('.bento').boundingBox())!

  expect(band.y, 'the band starts above the top bar').toBeGreaterThanOrEqual(bar.y + bar.height - 1)
  expect(band.y + band.height, 'the band runs into the row').toBeLessThanOrEqual(row.y + 1)
})

test('what is in the band does not move the row', async ({ page }) => {
  const full = (await page.locator('.bento').boundingBox())!
  const chips = await page.locator('.nudge').count()
  expect(chips, 'nothing in the band to take away: this house has nothing to attend to').toBeGreaterThan(0)

  // take the whole band away, and then give it more than it can hold
  await page.locator('.nudges').evaluate((el) => ((el as HTMLElement).hidden = true))
  await page.waitForTimeout(300)
  const empty = (await page.locator('.bento').boundingBox())!

  await page.locator('.nudges').evaluate((el) => {
    ;(el as HTMLElement).hidden = false
    const one = el.querySelector('.nudge')!
    for (let i = 0; i < 6; i++) el.append(one.cloneNode(true))
  })
  await page.waitForTimeout(300)
  const many = (await page.locator('.bento').boundingBox())!

  expect(empty.y, 'the row moved when the band emptied').toBe(full.y)
  expect(many.y, 'the row moved when the band filled up').toBe(full.y)
  expect(many.height, 'the row gave up height to the band').toBe(full.height)
})

test('a band that cannot fit its chips scrolls rather than growing', async ({ page }) => {
  const one = (await page.locator('.nudges').boundingBox())!.height
  const over = await page.locator('.nudges').evaluate((el) => {
    const chip = el.querySelector('.nudge')!
    for (let i = 0; i < 6; i++) el.append(chip.cloneNode(true))
    return { h: el.getBoundingClientRect().height, scrolls: el.scrollWidth > el.clientWidth + 1 }
  })
  expect(over.h, 'the band wrapped onto a second line').toBe(one)
  expect(over.scrolls, 'the chips that do not fit have nowhere to go').toBe(true)
})

/* What slice 5 of design/nightfall could not land, and said was the arrangement's to fix rather
   than the face's: a pane is a drawer only if the row you came from is still there above it. It
   never was, because Home led with a greeting and an attention strip and the row did not begin
   until well below where the pane stopped. */
test('an opened device stops short of the row, so the row is still there above it', async ({ page }) => {
  const card = (await page.locator('.bento-card').first().boundingBox())!
  await page.mouse.move(card.x + card.width / 2, card.y + 60)
  await page.mouse.down()
  await page.waitForTimeout(900)
  await page.mouse.up()
  await expect(page.locator('.opened-panel')).toHaveCount(1)
  await page.waitForTimeout(900)

  const pane = (await page.locator('.opened-panel').boundingBox())!
  const showing = pane.y - card.y
  expect(showing, 'the pane covers the row it came from, which makes it a new screen')
    .toBeGreaterThan(24)
  // and it is a sliver, not half the row: the board leaves the top of a card and its corner
  expect(showing, 'the pane stops so short of the row that it is not a drawer either')
    .toBeLessThan(card.height / 3)
})
