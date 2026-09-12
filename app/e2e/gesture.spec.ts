/* The gesture has two jobs and they must not collide: a tap controls the device, a hold opens it
   and controls nothing. The failure mode is silent — a lamp that switches off on its way into its
   detail — so nothing but a test in a real browser catches it. */
import { expect, test, type Page } from '@playwright/test'

const ROOM = '/?room=living&at=19:40'

async function settled(page: Page, url: string) {
  await page.goto(url, { waitUntil: 'networkidle' })
  await expect(page.locator('.tile').first()).toBeVisible()
  await page.waitForTimeout(700)          // the cards finish arriving before a gesture means anything
}

async function centre(page: Page, selector: string) {
  const el = page.locator(selector).first()
  await el.scrollIntoViewIfNeeded()
  await page.waitForTimeout(250)
  const box = (await el.boundingBox())!
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
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
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.waitForTimeout(520)        // past the hold threshold
    await page.mouse.up()

    await expect(page.locator('.opened-panel')).toHaveCount(1)
    // The panel shows the device as it was. If the hold had also toggled, this is where it shows.
    await expect(page.locator('.opened-big')).toContainText(before.split('%')[0])
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

    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.waitForTimeout(650)              // past the hold
    await page.mouse.up()
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
    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.waitForTimeout(150)
    await page.mouse.up()

    await expect(page.locator('.opened-panel')).toHaveCount(0)
    await expect(state).not.toHaveText(before, { timeout: 3000 })
  })
})
