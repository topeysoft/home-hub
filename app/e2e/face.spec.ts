/* The face, in the browser that is actually served the panel.

   This file exists because of one specific way a face can be entirely correct in the source and
   absent from the screen. panel.css used to declare `-webkit-backdrop-filter` by hand alongside the
   standard property; the CSS minifier read that pair as "the prefixed one covers every target" and
   emitted only the prefixed one. Chrome 153 removed the -webkit- alias, so every frosted surface in
   the BUILT panel -- the cards, the rail, both panes, the whole of glass -- went flat, while the
   source still plainly said blur and every unit test still passed. Nothing that reads the stylesheet
   can catch that. Only the built panel in a real browser can, which is what this is. */
import { expect, test, type Page } from '@playwright/test'

/* the standard property and the old alias, because which one survives the build is exactly the
   thing in question -- a surface is frosted if the browser ended up with either */
async function frost(page: Page, sel: string) {
  return page.evaluate((s) => {
    const el = document.querySelector(s)
    if (!el) return 'no such element'
    const cs = getComputedStyle(el)
    const std = cs.getPropertyValue('backdrop-filter')
    const wk = cs.getPropertyValue('-webkit-backdrop-filter')
    return [std, wk].find((v) => v && v !== 'none') ?? 'none'
  }, sel)
}

/* a room card on home, and a lamp inside a room: the two surfaces a person actually looks at.
   Not any `.tile` -- a camera turns its own frost off on purpose, because it brings a picture and
   is never overpainted. */
test('a card is frosted in the panel the browser is actually given', async ({ page }) => {
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.room-card').first()).toBeVisible()
  expect(await frost(page, '.room-card')).toContain('blur')
})

test('glass keeps its blur once the house is set to it', async ({ page }) => {
  await page.goto('/?face=glass&room=living&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.light').first()).toBeVisible()
  expect(await page.getAttribute('.shell', 'data-face')).toBe('glass')
  expect(await frost(page, '.tile.light')).toContain('blur')
})

test('a pane is frosted too, which is what makes it a pane', async ({ page }) => {
  await page.goto('/?face=glass&sheet=house&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.house-panel')).toBeVisible()
  expect(await frost(page, '.house-panel')).toContain('blur')
})
