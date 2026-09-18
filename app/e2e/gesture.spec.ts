// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The gesture has two jobs and they must not collide: a tap controls the device, a hold opens it
   and controls nothing. The failure mode is silent — a lamp that switches off on its way into its
   detail — so nothing but a test in a real browser catches it. */
import { expect, test, type Page } from '@playwright/test'

const ROOM = '/?room=living&at=19:40'
const HOME = '/?at=19:40'


/* Stop the page's clock, so a press can be measured out by hand instead of slept through.
 *
 * `install` looks like it does this and does not: it swaps the timer functions for fakes and leaves
 * the clock running, so `runFor` only ADDS to a wall clock still turning underneath. Measured -- a
 * 420ms timer set under a bare `install`, advanced by 150 and then left alone, goes off by itself
 * 1.5s later. `pauseAt` is the one that stops time, and it takes the PAGE's clock, not the runner's:
 * the two drift, and it refuses an instant in the past.
 *
 * It goes here, at the end of settling, rather than inside the press. Pausing jumps the clock
 * forward to the instant named, which fires whatever fell due in between -- and that is a real
 * event: a two second jump taken mid-test moved a tile's state out from under a reading the test
 * had already taken. Jumping before anything is measured means whatever lands, lands first, and
 * the test then measures the room it is actually looking at. */
async function freeze(page: Page) {
  await page.clock.install()
  /* As small a step as will still land ahead of the page: pausing JUMPS to the instant named and
     fires everything due in between, and a jump is not free -- at two seconds it expired the line
     on a card mid-test and the test read a room that had moved. The ladder is for a round trip that
     stalls past the cushion, which is the only way pauseAt can refuse. */
  for (const cushion of [100, 250, 600]) {
    try { return await page.clock.pauseAt(await page.evaluate(() => Date.now()) + cushion) }
    catch (e) { if (!/past/i.test(String(e))) throw e }
  }
  throw new Error('the page clock kept outrunning the cushion, so the press cannot be timed')
}

async function settled(page: Page, url: string) {
  await page.goto(url, { waitUntil: 'networkidle' })
  await expect(page.locator('.tile').first()).toBeVisible()
  await page.waitForTimeout(700)          // the cards finish arriving before a gesture means anything
  await freeze(page)
}

async function centre(page: Page, selector: string) {
  const el = page.locator(selector).first()
  await el.scrollIntoViewIfNeeded()
  await page.waitForTimeout(250)
  const box = (await el.boundingBox())!
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
}

/* Hold for exactly this long, with the clock already stopped by `settled`.
 *
 * These tests sit either side of one number -- HOLD in hold.ts, 420ms -- and a test that sleeps
 * against it is not asserting anything about the panel, it is betting the machine stays
 * responsive. Six workers and a second session's suite are enough to lose that bet: a 270ms stall
 * inside a 150ms sleep turns a tap into a hold, and input dispatch lagging by 100ms turns a hold
 * back into a tap. It failed both ways for real, picking a different test each run, which is the
 * tell that it was never a regression. Time is handed back the moment the finger lifts, so what
 * the release sets off -- the pane rising, a light toggling -- happens in real time as before. */
async function press(page: Page, x: number, y: number, ms: number) {
  await page.mouse.move(x, y)
  try {
    await page.mouse.down()
    await page.clock.runFor(ms)
    await page.mouse.up()
  } finally {
    await page.clock.resume()     // even if an assertion throws: a stopped clock would follow the page through the rest of the test
  }
}

test.describe('with a mouse', () => {
  test('a tap still toggles the light, and toggles it back', async ({ page }) => {
    await settled(page, ROOM)
    const state = page.locator('.tile.light .tile-state').first()
    const before = await state.innerText()

    const { x, y } = await centre(page, '.tile.light')
    await page.mouse.click(x, y)
    await expect(state).not.toHaveText(before, { timeout: 3000 })

    await page.mouse.click(x, y)
    await expect(state).toHaveText(before, { timeout: 3000 })
  })

  test('a hold opens the device and does not touch it on the way', async ({ page }) => {
    await settled(page, ROOM)
    const before = await page.locator('.tile.light .tile-state').first().innerText()

    const { x, y } = await centre(page, '.tile.light')
    await press(page, x, y, 520)         // past the hold threshold

    await expect(page.locator('.opened-panel')).toHaveCount(1)
    // The panel shows the device as it was. If the hold had also toggled, this is where it shows.
    // The number, not the tile's sentence: the tile says "On, 35%" and the pane says "35%", and what
    // is being asserted is that the two are the same light -- not how either of them words it.
    await expect(page.locator('.opened-big')).toContainText(before.match(/\d+/)?.[0] ?? before)
  })

  test('the card lets go of the pointer when a hold opened it', async ({ page }) => {
    /* The hold swallows the release so the light does not toggle on its way in (see hold.ts). The card
       was never told the pointer had gone, and went on dimming to a mouse that was only passing over it
       afterwards. Nothing but a real browser sees this: it needs a capture, a swallowed release, and a
       move with no button held. */
    await settled(page, ROOM)
    const fill = page.locator('.tile.light.dimmable .fill').first()
    const { x, y } = await centre(page, '.tile.light.dimmable')
    const box = (await page.locator('.tile.light.dimmable').first().boundingBox())!

    await press(page, x, y, 650)                // past the hold
    await expect(page.locator('.opened')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.locator('.opened')).toHaveCount(0)

    const settledWidth = await fill.evaluate(e => (e as HTMLElement).style.width)
    for (const frac of [0.2, 0.9]) {
      await page.mouse.move(box.x + box.width * frac, box.y + box.height / 2)
      await page.waitForTimeout(120)
      expect(await fill.evaluate(e => (e as HTMLElement).style.width)).toBe(settledWidth)
    }
  })

  test('a hold that is released early is still only a tap', async ({ page }) => {
    await settled(page, ROOM)
    const state = page.locator('.tile.light .tile-state').first()
    const before = await state.innerText()

    const { x, y } = await centre(page, '.tile.light')
    await press(page, x, y, 150)         // let go well before it

    await expect(page.locator('.opened-panel')).toHaveCount(0)
    await expect(state).not.toHaveText(before, { timeout: 3000 })
  })

  /* The third thing on a card, after the tap and the hold: a control drawn inside it. The hold
     captures the pointer so a finger may drift off the card's edge, and a capture retargets
     everything that follows at the card -- the click included. A thermostat's step buttons never
     heard their own tap, on every arrangement, and nothing said so: the card simply did not move. */
  test('a step button inside a card takes its own tap', async ({ page }) => {
    await settled(page, HOME)                 // the row's thermostat is the card that carries them
    const big = page.locator('.bento .tile.climate .clim-big').first()
    const before = (await big.innerText()).trim()

    await page.locator('.bento .tile.climate .clim-btn[aria-label="Raise the target"]').first().click()
    await expect(big).not.toHaveText(before, { timeout: 3000 })
    // one step, in the house's unit -- not the ceiling a Celsius clamp put a Fahrenheit house at
    const after = Number((await big.innerText()).match(/-?\d+(\.\d+)?/)![0])
    expect(Math.abs(after - Number(before.match(/-?\d+(\.\d+)?/)![0]))).toBeLessThanOrEqual(1)

    await expect(page.locator('.opened-panel'), 'the tap opened the device as well').toHaveCount(0)
  })

  /* The card still opens: the control keeps its own tap, it does not take the card's gesture. */
  test('holding a card that has controls in it still opens the device', async ({ page }) => {
    await settled(page, HOME)
    const { x, y } = await centre(page, '.bento .tile.climate')
    await press(page, x, y - 40, 520)         // the card, not one of its buttons
    await expect(page.locator('.opened-panel')).toHaveCount(1)
  })
})
