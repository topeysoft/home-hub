// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What is playing, on the wall: the card design/player/RowA.dc.html draws, chosen 24 September.

   The cover is the card, and the controls ride on one pane of glass across its foot -- the title,
   a hairline for where it is up to, the transport, and then how loud, as a fourth line. These pin
   that order and that the glass stays at the foot, because a card that quietly went back to one
   crowded row of buttons over a darkened picture would pass every other test in the suite. */
import { expect, test } from '@playwright/test'

const CARD = '.wall-stage .bento .tile.media'

test.beforeEach(async ({ page }) => {
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator(CARD).first()).toBeVisible()
  await page.waitForTimeout(1500)                 // past the row's arrival
})

const box = async (page: import('@playwright/test').Page, sel: string) => {
  const b = await page.locator(`${CARD} ${sel}`).first().boundingBox()
  expect(b, `${sel} is not on the card`).not.toBeNull()
  return b!
}

test('the controls ride on one pane of glass at the foot of the cover', async ({ page }) => {
  const card = (await page.locator(CARD).first().boundingBox())!
  const glass = await box(page, '.media-foot')
  // inset the same on three sides, as drawn: 14 on a 332 card, so a little under at the wall's size
  for (const [side, gap] of [['left', glass.x - card.x], ['right', card.x + card.width - glass.x - glass.width],
    ['bottom', card.y + card.height - glass.y - glass.height]] as const)
    expect(gap, `the glass is not inset from the card's ${side}`).toBeGreaterThan(8)
  // the cover keeps the top half of the card to itself
  expect(glass.y - card.y, 'the glass has climbed over the picture').toBeGreaterThan(card.height * 0.4)
  expect(await page.locator(`${CARD} .media-foot`).first().evaluate(e => getComputedStyle(e).backdropFilter))
    .toContain('blur')
})

test('which player it is, as a chip at the top, not a line above the title', async ({ page }) => {
  const card = (await page.locator(CARD).first().boundingBox())!
  const chip = await box(page, '.media-which')
  expect(chip.y - card.y).toBeLessThan(30)
  expect(chip.x - card.x).toBeLessThan(30)
  await expect(page.locator(`${CARD} .media-text .tile-name`).first()).toBeHidden()
})

test('title, where it is, the transport, then how loud -- in that order, down the glass', async ({ page }) => {
  const title = await box(page, '.media-title')
  const bar = await box(page, '.media-bar')
  const play = await box(page, '.ctl.primary')
  const vol = await box(page, '.vol')
  const glass = await box(page, '.media-foot')
  expect(bar.y, 'the progress line is not under the title').toBeGreaterThan(title.y + title.height - 1)
  expect(play.y, 'the transport is not under the progress line').toBeGreaterThan(bar.y + bar.height - 1)
  expect(vol.y, 'the volume is not under the transport').toBeGreaterThan(play.y + play.height - 1)
  // both lines run the width of the glass; the transport sits in its middle
  for (const [what, b] of [['progress', bar], ['volume', vol]] as const)
    expect(b.width, `the ${what} line does not span the glass`).toBeGreaterThan(glass.width * 0.7)
  expect(Math.abs(play.x + play.width / 2 - (glass.x + glass.width / 2)), 'pause is not centered').toBeLessThan(4)
})

test('nothing the board left out: no off button, no "Playing" word, no heart', async ({ page }) => {
  await expect(page.locator(`${CARD} .ctl.power`).first()).toBeHidden()
  await expect(page.locator(`${CARD} .media-when`).first()).toBeHidden()
  await expect(page.locator(`${CARD} [aria-label*="ike"]`)).toHaveCount(0)
})

test('the volume thickens under a finger, says no number, and the speaker hears the new level', async ({ page }) => {
  /* No figure beside it, held or not: the first build said one, and a number changing under the
     finger read as more confusing than the line on its own (24 September). */
  const vol = page.locator(`${CARD} .vol`).first()
  const input = vol.locator('input')
  const sent = page.waitForRequest(r => r.method() === 'POST' && /\/volume$/.test(r.url()))
  const b = (await input.boundingBox())!
  await page.mouse.move(b.x + b.width * 0.35, b.y + b.height / 2)
  await page.mouse.down()
  await page.mouse.move(b.x + b.width * 0.2, b.y + b.height / 2, { steps: 4 })
  await expect(vol).toHaveClass(/vol-held/)
  expect((await vol.innerText()).trim(), 'the volume is saying a number').toBe('')
  await page.mouse.up()
  await sent
  await expect(vol).not.toHaveClass(/vol-held/)
})
