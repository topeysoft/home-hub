// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Light or dark (design/appearance/, B, decided 7 October).
 *
 * Each screen picks for itself and keeps it in its own browser: a wall that nobody set stays dark, a
 * phone follows the phone, and what is picked on the Look page outlives a reload and never reaches
 * the hub. And light means the page is drawn for a light field -- dark ink, no veil -- which is what
 * a screenshot cannot be asked to check and a computed style can. */
import { expect, test } from '@playwright/test'

const shadeOf = (page: import('@playwright/test').Page) => page.evaluate(() => document.documentElement.dataset.shade)

test('a wall nobody has set stays dark, whatever the room it is in', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  expect(await shadeOf(page)).toBe('dark')
})

test('a phone follows the phone until somebody picks', async ({ browser }) => {
  for (const colorScheme of ['light', 'dark'] as const) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme })
    const page = await ctx.newPage()
    await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
    expect(await shadeOf(page)).toBe(colorScheme)
    await ctx.close()
  }
})

test('picking Light on the Look page sticks to this screen, and the hub is never told', async ({ page }) => {
  const told: string[] = []
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/look')) told.push(r.postData() ?? '') })
  await page.goto('/?sheet=look&at=19:40', { waitUntil: 'networkidle' })
  await page.locator('.shade-opt', { hasText: 'Light' }).click()
  expect(await shadeOf(page)).toBe('light')
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  expect(await shadeOf(page)).toBe('light')
  expect(told).toEqual([])
})

test('light is drawn for a light field: dark ink, no veil, a sky that is not dark', async ({ page }) => {
  await page.goto('/?shade=light&at=23:40', { waitUntil: 'networkidle' })
  await page.waitForTimeout(400)
  const seen = await page.evaluate(() => {
    const lum = (c: string) => { const [r, g, b] = c.match(/[\d.]+/g)!.map(Number); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 }
    const veil = document.querySelector('.sky-veil')
    const sky = document.querySelector('canvas.sky') as HTMLCanvasElement
    const px = sky.getContext('2d')!.getImageData(Math.round(sky.width / 2), Math.round(sky.height * 0.3), 1, 1).data
    return {
      ink: lum(getComputedStyle(document.body).color),
      veil: veil ? getComputedStyle(veil).display : 'none',
      sky: (0.2126 * px[0] + 0.7152 * px[1] + 0.0722 * px[2]) / 255,
    }
  })
  expect(seen.ink).toBeLessThan(0.2)
  expect(seen.veil).toBe('none')
  expect(seen.sky).toBeGreaterThan(0.55)       // midnight, and still a light sky
})
