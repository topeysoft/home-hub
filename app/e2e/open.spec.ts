/* Holding a card open. The home behind it has to actually recede — that is what makes the opened
   device read as being in front of the house rather than on top of it. A settled screenshot cannot
   tell you whether it moved, only where it ended up, so this reads the transform as it happens. */
import { expect, test, type Page } from '@playwright/test'

async function stage(page: Page) {
  return page.evaluate(() => {
    const s = document.querySelector('.shell')!, st = document.querySelector('.stage')!
    const cs = getComputedStyle(st)
    return { shellClass: s.className, transform: cs.transform, filter: cs.filter }
  })
}

async function holdOpen(page: Page) {
  const tile = page.locator('.tile.light').first()
  const box = (await tile.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.waitForTimeout(470)      // past the hold threshold: the panel is on its way
  await page.mouse.up()
}

test.beforeEach(async ({ page }) => {
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.light').first()).toBeVisible()
  await page.waitForTimeout(700)
})

test('the house is untouched until something is opened', async ({ page }) => {
  const before = await stage(page)
  expect(before.transform === 'none' || before.transform === 'matrix(1, 0, 0, 1, 0, 0)').toBe(true)
  await expect(page.locator('.opened-panel')).toHaveCount(0)
})

test('holding a card opens it and pushes the house back', async ({ page }) => {
  const before = await stage(page)
  await holdOpen(page)
  await expect(page.locator('.opened-panel')).toHaveCount(1)
  await page.waitForTimeout(850)          // let the transition settle

  const after = await stage(page)
  expect(after, 'the house behind did not move at all').not.toEqual(before)
  expect(after.shellClass).not.toBe(before.shellClass)
})

test('closing gives the house back exactly as it was', async ({ page }) => {
  const before = await stage(page)
  await holdOpen(page)
  await expect(page.locator('.opened-panel')).toHaveCount(1)
  await page.waitForTimeout(850)

  await page.locator('.opened-close').click()
  await expect(page.locator('.opened-panel')).toHaveCount(0)
  await page.waitForTimeout(850)

  expect(await stage(page)).toEqual(before)
})

test('the opened device says what it is, not a blank panel', async ({ page }) => {
  await holdOpen(page)
  const panel = page.locator('.opened-panel')
  await expect(panel).toHaveCount(1)
  const text = await panel.innerText()
  expect(text.trim().length).toBeGreaterThan(3)
  expect(text).not.toContain('undefined')
})
