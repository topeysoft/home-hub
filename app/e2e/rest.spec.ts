/* The panel resting with something left open in front of it.
 *
 * The resting screen is the sky, the clock, and three lines about the house — and it is drawn ABOVE
 * everything else on the shell. Every part of the house recedes for it: the rail, the stage, the
 * bars. A device pane did not, so a lamp opened at bedtime sat there fully lit with the time
 * floating over it and no sky behind it at all, which reads as a rendering fault rather than as a
 * house at rest.
 *
 * The clock is Playwright's rather than a three-minute wait, and jumped rather than run: the panel
 * keeps several intervals, and running four minutes of them tick by tick takes longer than the wait
 * it replaces.
 */
import { expect, test, type Page } from '@playwright/test'

const REST_AFTER = '04:00'

async function holdOpen(page: Page) {
  const tile = page.locator('.tile.light.dimmable').first()
  await expect(tile).toBeVisible()
  await page.waitForTimeout(600)
  const box = (await tile.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
  await page.mouse.down()
  await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10000 })
  await page.mouse.up()
  await page.waitForTimeout(700)
}

test('the house at rest takes an opened device with it', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  await holdOpen(page)

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()
  await page.waitForTimeout(1200)             // the fade is 0.9s

  const pane = page.locator('.opened')
  await expect(pane).toHaveCSS('opacity', '0')
  /* and it takes no touches while it cannot be seen: the first press on a resting screen is the one
     that wakes it, and it must not also land on the veil of a pane nobody can see */
  await expect(pane).toHaveCSS('pointer-events', 'none')
  await expect(page.locator('.idle-time')).toBeVisible()
})

test('waking brings the house back, not what was left open', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  await holdOpen(page)

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()
  await page.waitForTimeout(1000)

  await page.mouse.click(720, 450)
  await page.waitForTimeout(1000)
  await expect(page.locator('.idle')).toHaveCount(0)
  await expect(page.locator('.opened-panel'), 'the pane came back with the house').toHaveCount(0)
  await expect(page.locator('.shell')).not.toHaveClass(/opened-shell/)
  await expect(page.locator('.stage')).toHaveCSS('opacity', '1')
})
