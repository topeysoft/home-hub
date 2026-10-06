// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Cameras tab fits on the screen it is on.
 *
 * What made this a spec: the tab was a grid that wrapped downwards inside a stage that scrolled,
 * and a camera tile is `.tile.wide` -- two columns of a grid this screen does not have -- so each
 * camera took a row of its own. Three of them were 1483px of column inside a 618px stage: the
 * heading scrolled off the top and the last camera sat behind the command box, where a wall panel
 * has no way to reach it.
 *
 * So the rule, the Rooms tab's rule: the stage does not scroll, the head keeps its place, and a
 * house with more cameras than fit runs off to the RIGHT rather than below a fold nobody on a wall
 * can cross. Sizes are read from inside the page rather than from a screenshot -- what is being
 * asserted is where things are, not what they look like.
 */
import { expect, test, type Page } from '@playwright/test'

async function openCameras(page: Page) {
  await page.goto('/?nav=top&at=13:00', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /^Cameras$/ }).click()
  await expect(page.locator('.cameras-all .tile.camera').first()).toBeVisible()
  await page.waitForTimeout(1200)       // the entrance, and the measure that follows it
}

/** Where everything is, as the panel has actually laid it out. */
const measure = (page: Page) =>
  page.evaluate(() => {
    const stage = document.querySelector('.stage')!
    const grid = document.querySelector('.cameras-all')!
    const bar = document.querySelector('.bottombar')?.getBoundingClientRect().top ?? innerHeight
    const tiles = [...document.querySelectorAll('.cameras-all .tile.camera')].map(t => t.getBoundingClientRect())
    const head = document.querySelector('.cameras .stage-head')!.getBoundingClientRect()
    return {
      stageScrollsDown: stage.scrollHeight - stage.clientHeight,
      gridRunsRight: grid.scrollWidth - grid.clientWidth,
      pageScrollsSideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      belowTheFold: tiles.filter(r => r.bottom > innerHeight).length,
      behindTheBar: tiles.filter(r => r.bottom > bar + 1).length,
      headTop: Math.round(head.top),
      widest: tiles.reduce((w, r) => Math.max(w, r.width / r.height), 0),
      n: tiles.length,
    }
  })

test('every camera is on the screen, and the heading stays with them', async ({ page }) => {
  await openCameras(page)
  const m = await measure(page)
  expect(m.n, 'the house has cameras to show').toBeGreaterThan(0)
  expect(m.stageScrollsDown, 'the stage scrolls down, so the heading can be scrolled away').toBe(0)
  expect(m.belowTheFold, 'a camera is cut off by the bottom of the screen').toBe(0)
  expect(m.behindTheBar, 'a camera is behind the command box').toBe(0)
})

test('a picture is never squeezed past 4:3 to fill the stage', async ({ page }) => {
  await openCameras(page)
  const m = await measure(page)
  /* A camera sends 16:9 and the tile crops to its cell, so a cell taller than 4:3 throws away the
     sides of the scene -- the two thirds of the drive the camera was put up to watch. Rather than
     stretch that far the stage is left short, which is what the sky is for. */
  expect(m.widest, 'a frame was squeezed past 4:3').toBeGreaterThanOrEqual(4 / 3 - 0.02)
})

test('when they do not fit across, the house runs right rather than below the fold', async ({ page }) => {
  await page.setViewportSize({ width: 560, height: 800 })    // narrow enough that three frames cannot sit in a row
  await openCameras(page)
  const m = await measure(page)
  expect(m.gridRunsRight, 'there is nothing to the right, so they went somewhere else').toBeGreaterThan(0)
  expect(m.stageScrollsDown, 'they went below the fold instead of off to the right').toBe(0)
  expect(m.belowTheFold, 'a camera is cut off by the bottom of the screen').toBe(0)
  expect(m.pageScrollsSideways, 'the page itself scrolls sideways, which a wall cannot do').toBeLessThanOrEqual(1)
})
