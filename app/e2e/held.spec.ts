// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The wall awake holds still behind its frosted cards.

   On the wall's GPU (a Pi 5, the same as the CM5's) every frosted pane re-blurs whenever anything
   behind it moves: with the sky and the orb looping, the GPU sat at 98% and Home drew 15 frames a
   second; held, it does nothing at idle and every frame makes 60. So on the wall, awake, nothing may
   loop and the sky canvas is not redrawn; at rest, where there is little glass, everything moves
   again; and a phone or tablet, which has the GPU for it, is never held. A new looping animation
   added anywhere on Home fails the first test, which is the point. */
import { expect, test, type Page } from '@playwright/test'

const loops = (page: Page) => page.evaluate(() =>
  document.getAnimations().filter((a) => a.playState === 'running' && a.effect?.getTiming().iterations === Infinity)
    .map((a) => (a as CSSAnimation).animationName))
const skyMoves = (page: Page) => page.evaluate(async () => {
  const sky = document.querySelector<HTMLCanvasElement>('canvas.sky')!
  const before = sky.toDataURL()
  await new Promise((r) => setTimeout(r, 1200))
  return sky.toDataURL() !== before
})

test('on the wall, awake, nothing loops and the sky is drawn once', async ({ page }) => {
  await page.goto('/?wall=1&at=22:30')
  await expect(page.locator('.shell[data-held]')).toHaveCount(1)
  await page.waitForTimeout(1500)
  expect(await loops(page)).toEqual([])
  expect(await skyMoves(page)).toBe(false)
})

test('on the wall at rest, the sky and the orb move again', async ({ page }) => {
  await page.goto('/?wall=1&rest=1&at=22:30')
  await expect(page.locator('.shell.resting')).toHaveCount(1)
  await expect(page.locator('.shell[data-held]')).toHaveCount(0)
  await expect.poll(() => skyMoves(page)).toBe(true)
})

test('a phone or tablet is never held', async ({ page }) => {
  await page.goto('/?at=22:30')
  await expect(page.locator('.shell[data-held]')).toHaveCount(0)
  await expect.poll(() => skyMoves(page)).toBe(true)
})

test('on the wall, a strip drops its frost while it scrolls and gets it back when it stops', async ({ page }) => {
  await page.goto('/?wall=1&at=22:30')
  const [before, during, after] = await page.locator('.bento').evaluate(async (el) => {
    const frosted = () => [...el.querySelectorAll('*')].filter((n) => getComputedStyle(n).backdropFilter !== 'none').length
    const first = frosted()
    let mid = -1
    el.addEventListener('scroll', () => { if (mid < 0) mid = frosted() }, { once: true })
    const ended = new Promise((r) => el.addEventListener('scrollend', r, { once: true }))
    el.scrollBy({ left: 600 })
    await ended
    await new Promise((r) => requestAnimationFrame(r))
    return [first, mid, frosted()]
  })
  expect(before).toBeGreaterThan(0)
  expect(during).toBe(0)
  expect(after).toBe(before)
})

test('the wall is touched, not pointed at: no pointer arrow', async ({ page }) => {
  await page.goto('/?wall=1&at=22:30')
  expect(await page.locator('.bento').evaluate((el) => getComputedStyle(el).cursor)).toBe('none')
  await page.goto('/?at=22:30')
  expect(await page.locator('.bento').evaluate((el) => getComputedStyle(el).cursor)).not.toBe('none')
})
