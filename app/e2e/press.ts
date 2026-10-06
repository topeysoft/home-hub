// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Holding something, without betting on a wall clock.
 *
 * `hold.ts` opens a pane after HOLD = 420ms. A test that presses for 520 and expects a hold has
 * 100ms of tolerance; one that presses for 150 and expects a tap has 270ms. Under two projects at
 * six workers -- or another session's suite on the same machine -- both are reachable, and when they
 * go they go as a DIFFERENT test each time, which is what makes them read as somebody's regression
 * rather than as the clock. Four sightings across three sessions before the cause was found.
 *
 * So the page's clock stops and the press is advanced by hand. Three things about that are not
 * obvious, and each one cost home-hub-02 a run when they wrote this for the gesture specs:
 *
 * `install` looks like it stops time and does not -- it swaps the timer functions for fakes and
 * leaves the clock turning underneath, so `runFor` only ADDS to it. A 420ms timer set under a bare
 * `install`, advanced by 150 and then left alone, still goes off by itself. `pauseAt` is the one
 * that stops time.
 *
 * `pauseAt` takes the PAGE's clock, not the runner's. The two drift and it refuses an instant in
 * the past, so the instant is read out of the page with a small step added for the round trip.
 *
 * And the step stays small because pausing JUMPS: everything due between now and the instant named
 * fires at once. Two seconds of it expired a line on a card mid-test, and the test then measured a
 * room that had moved out from under its own baseline.
 *
 * Lifted here from `gesture.spec.ts` so the other specs that hold things can stop betting too.
 */
import { type Page } from '@playwright/test'

/** Stop the page's clock, so a press is measured in advances and not in seconds. */
export async function freeze(page: Page) {
  await page.clock.install()
  /* the ladder is for a round trip that stalls past the cushion, which is the only way pauseAt can
     refuse -- and refusing is the one failure here that must not be silent */
  for (const cushion of [100, 250, 600]) {
    try { return await page.clock.pauseAt(await page.evaluate(() => Date.now()) + cushion) }
    catch (e) { if (!/past/i.test(String(e))) throw e }
  }
  throw new Error('the page clock kept outrunning the cushion, so the press cannot be timed')
}

/** Press at (x, y) for `ms` of the page's own time. `freeze` first. */
export async function press(page: Page, x: number, y: number, ms: number) {
  await page.mouse.move(x, y)
  try {
    await page.mouse.down()
    await page.clock.runFor(ms)
    await page.mouse.up()
  } finally {
    /* even if an assertion throws: a stopped clock would follow the page through the rest of the
       test, and what the release sets off -- the pane rising, a light toggling -- happens in real
       time */
    await page.clock.resume()
  }
}
