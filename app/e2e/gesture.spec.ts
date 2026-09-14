/* The gesture has two jobs and they must not collide: a tap controls the device, a hold opens it
   and controls nothing. The failure mode is silent — a lamp that switches off on its way into its
   detail — so nothing but a test in a real browser catches it. */
import { expect, test, type Page } from '@playwright/test'

const ROOM = '/?room=living&at=19:40'
const HOME = '/?at=19:40'

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
    await page.mouse.move(x, y - 40)          // the card, not one of its buttons
    await page.mouse.down()
    await page.waitForTimeout(520)
    await page.mouse.up()
    await expect(page.locator('.opened-panel')).toHaveCount(1)
  })
})
