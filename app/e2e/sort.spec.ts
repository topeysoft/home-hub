// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* New devices reaches every device it is listing.
 *
 * What made this a spec: this screen borrows `.room` for its shell, so it inherited the rule that
 * stops the stage above a room scrolling. That rule is right for a ROOM -- what overflows there
 * goes sideways, and it is what keeps the way back from scrolling off the top of a wall panel with
 * no keyboard and no Escape. But New devices has no sideways anything. It is a column of rows, and
 * a house with more unplaced things than fit a screen simply had the rest of them out of reach:
 * fourteen found devices on a 1280x800 wall put the last one at y 1408, under the command box,
 * with nothing on the screen that could be scrolled to get to it.
 *
 * So the scroll goes on everything UNDER THE HEAD rather than back on the stage, which keeps both
 * things true at once: every device is reachable, and the head -- the way back with it -- never
 * moves. Everything under the head and not the list alone: the bars that teach this screen stand
 * between the two, and held fixed above a scrolling list they ate a short wall themselves, leaving
 * a 69px window for a 135px row -- so no row could be read whole however far it was scrolled.
 * Measured from inside the page, because what is being asserted is what a finger can reach.
 */
import { expect, test, type Page } from '@playwright/test'

/* Short on purpose. The mock house has two things waiting to be placed, which fit a full wall with
   room to spare; a wall this short is the same house on a panel that cannot show them all, and it
   is the house with fourteen of them without needing a second mock to say so. */
const SHORT = { width: 1280, height: 560 }

async function openNewDevices(page: Page) {
  await page.goto('/?nav=top&at=19:40', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /^Rooms$/ }).click()
  await page.getByRole('button', { name: 'Open New devices' }).click()
  await expect(page.locator('.sort-row').first()).toBeVisible()
  await page.waitForTimeout(900)          // the entrance, and the measure that follows it
}

/** Where everything is, as the panel has actually laid it out. */
const measure = (page: Page) =>
  page.evaluate(() => {
    const stage = document.querySelector('.stage')!
    const list = document.querySelector('.sort-scroll')!
    const back = document.querySelector('.back')!.getBoundingClientRect()
    const rows = [...document.querySelectorAll('.sort-row')]
    const last = rows[rows.length - 1].getBoundingClientRect()
    const bar = document.querySelector('.bottombar')?.getBoundingClientRect().top ?? innerHeight
    // what is clipped by the list is not gone, it is scrolled -- so the last row is judged against
    // the list's own window, which is the thing a finger moves
    const win = list.getBoundingClientRect()
    return {
      n: rows.length,
      stageScrollsDown: stage.scrollHeight - stage.clientHeight,
      listScrollsDown: list.scrollHeight - list.clientHeight,
      lastRowInWindow: last.top >= win.top - 1 && last.bottom <= win.bottom + 1,
      listClearsTheBar: win.bottom <= bar + 1,
      backTop: Math.round(back.top),
    }
  })

test('the list scrolls, and the stage under it does not', async ({ page }) => {
  await page.setViewportSize(SHORT)
  await openNewDevices(page)
  const m = await measure(page)
  expect(m.n, 'the house has nothing waiting to be placed, so there is nothing to reach').toBeGreaterThan(0)
  expect(m.listScrollsDown, 'more devices than fit, and no way to scroll to them').toBeGreaterThan(0)
  expect(m.stageScrollsDown, 'the stage scrolls, so the way back can be scrolled off the top').toBe(0)
  expect(m.listClearsTheBar, 'the list runs under the command box, where a wall cannot reach it').toBe(true)
})

test('the last device can be reached, and the way back stays where it was', async ({ page }) => {
  await page.setViewportSize(SHORT)
  await openNewDevices(page)
  const before = await measure(page)
  expect(before.lastRowInWindow, 'this wall already shows them all, so it is not the case under test').toBe(false)

  // The whole point: a finger on the list, wound on until the list stops moving. It used to be twelve
  // turns of the wheel, which is a distance and not a condition -- SWITCHES=11 and a row that grew a
  // line both put the last device further down than 1440px, and the spec then failed for the length
  // of the list rather than for anything it is about.
  await page.locator('.sort-scroll').hover()
  const atBottom = () => page.evaluate(() => {
    const l = document.querySelector('.sort-scroll')!
    return l.scrollTop >= l.scrollHeight - l.clientHeight - 1
  })
  for (let i = 0; i < 80 && !(await atBottom()); i++) { await page.mouse.wheel(0, 120); await page.waitForTimeout(30) }
  await page.waitForTimeout(400)

  const after = await measure(page)
  expect(after.lastRowInWindow, 'the last device still cannot be reached').toBe(true)
  expect(after.backTop, 'the way back moved when the list was scrolled').toBe(before.backTop)
})
