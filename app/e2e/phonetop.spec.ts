// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The phone's top, pinned to the boards chosen on 2 October (design/band/: NameThenSky, LineChipsBC,
 * KindsB-house). Opened from the Home Screen, an iPhone draws the page under its status bar; the panel
 * leaves it its room, has no clock of its own on a phone, reads the house then its sky along the top
 * row, keeps a line for what needs you and puts the news in one row of chips, and moves what the house
 * would like finished into This house. The wall keeps its clock and its band.
 *
 * A browser will not report a status bar, so --safe-top is given the iPhone's 47 here: that is the one
 * value the panel reads it through (panel.css, the phone's top).
 */
import { expect, test, type Page } from '@playwright/test'

const STATUS_BAR = 47

async function phone(page: Page, q: string) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(q, { waitUntil: 'networkidle' })
  await page.addStyleTag({ content: `:root { --safe-top: ${STATUS_BAR}px !important }` })
  await page.waitForTimeout(800)
}

/* everything a finger or an eye is for, that starts inside the status bar */
const underStatusBar = (page: Page) => page.evaluate((top) =>
  [...document.querySelectorAll('button, a, input, h1, h2, .display, .link, .topbar-wx')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < top && r.bottom > 0 })
    .map(e => e.className || e.tagName), STATUS_BAR)

test.describe('on a phone', () => {
  test('nothing on Home or This house sits under the status bar', async ({ page }) => {
    await phone(page, '/?layout=wall&nav=top&at=19:40')
    expect(await underStatusBar(page)).toEqual([])
    await phone(page, '/?layout=wall&nav=top&at=19:40&sheet=house')
    expect(await underStatusBar(page)).toEqual([])
    await phone(page, '/?at=19:40')                      // the side list, which on a phone is a row across the top
    expect(await underStatusBar(page)).toEqual([])
  })

  test('the top row is the house, then its sky, then the two doors, and there is no clock', async ({ page }) => {
    await phone(page, '/?layout=wall&nav=top&at=19:40')
    await expect(page.locator('.topbar-time')).toBeHidden()
    const [link, wx, add, house] = await Promise.all(['.topbar .link', '.topbar-wx', '.topbar-add:not(.topbar-house)', '.topbar-house']
      .map(async s => (await page.locator(s).boundingBox())!))
    expect(link.y, 'the row starts under the status bar').toBeGreaterThanOrEqual(STATUS_BAR)
    for (const b of [wx, add, house]) expect(Math.abs((b.y + b.height / 2) - (link.y + link.height / 2)), 'one row').toBeLessThan(6)
    expect(link.x, 'the house leads').toBeLessThan(wx.x)
    expect(wx.x - (link.x + link.width), 'its sky right after it').toBeLessThan(24)
    expect(house.x + house.width, 'the menu at the far end').toBeGreaterThan(390 - 24)
    expect(add.x, 'Add beside it').toBeGreaterThan(wx.x + wx.width + 40)
  })

  test('the news is one row of chips, and setup is in This house', async ({ page }) => {
    await phone(page, '/?layout=wall&nav=top&at=19:40')
    const found = page.locator('.nudge-news .nudge', { hasText: 'new things nearby' })
    await expect(found).toBeVisible()
    expect((await found.boundingBox())!.height, 'a chip, not a line').toBeLessThanOrEqual(44)
    await expect(found.locator('.nudge-sub')).toBeHidden()
    await expect(page.locator('.nudges .nudge', { hasText: 'Lock the settings' }), 'setup left the band').toHaveCount(0)
    await expect(page.locator('.topbar-house.attention'), 'the menu says something is left').toHaveCount(1)

    await page.locator('.topbar-house').click()
    const finish = page.locator('.finish')
    await expect(finish).toBeVisible()
    await expect(finish.locator('.finish-step', { hasText: 'Set a passcode' })).toBeVisible()
    const doors = (await page.locator('.doors').boundingBox())!
    expect((await finish.boundingBox())!.y, 'at the top of This house').toBeLessThan(doors.y)
  })

  test('a row with more news than fits sweeps sideways rather than growing', async ({ page }) => {
    await phone(page, '/?layout=wall&nav=top&at=19:40')
    const row = page.locator('.nudge-news')
    const one = (await row.boundingBox())!.height
    const over = await row.evaluate((el) => {
      const chip = el.querySelector('.nudge')!
      for (let i = 0; i < 5; i++) el.append(chip.cloneNode(true))
      return { h: el.getBoundingClientRect().height, scrolls: el.scrollWidth > el.clientWidth + 1 }
    })
    expect(over.h).toBe(one)
    expect(over.scrolls).toBe(true)
  })
})

test('the wall keeps its clock, and its band as it was', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.topbar-time')).toBeVisible()
  await expect(page.locator('.nudges .nudge', { hasText: 'Lock the settings' })).toBeVisible()
  await expect(page.locator('.finish')).toHaveCount(0)
})
