/* The same gesture, made with a finger. A touch long-press is also the browser's own gesture, and
   the wall panel is a touch screen, so a mouse-only pass proves less than it looks like. This
   dispatches touch through CDP, the path a real finger takes. */
import { expect, test, type Page } from '@playwright/test'

const ROOM = '/?room=living&at=19:40'

async function settled(page: Page, url: string) {
  await page.goto(url, { waitUntil: 'networkidle' })
  await expect(page.locator('.tile').first()).toBeVisible()
  await page.waitForTimeout(700)
}

async function centre(page: Page, selector: string) {
  const el = page.locator(selector).first()
  await el.scrollIntoViewIfNeeded()          // a finger cannot press what is below the fold
  await page.waitForTimeout(250)
  // measured immediately before the press: Home's layout shifts as async blocks land above, so an
  // earlier box is stale by the time the finger arrives
  const box = (await el.boundingBox())!
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
}

async function press(page: Page, x: number, y: number, ms: number) {
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
  await page.waitForTimeout(ms)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await cdp.detach()
}

test.describe('with a finger', () => {
  for (const [what, url, selector] of [
    ['a light tile in a room', ROOM, '.tile.light'],
    ['a plain tile in a room', ROOM, '.tile.plain'],
    ['a card on Home', '/?layout=rail&at=19:40', '.bento-card'],
  ] as const) {
    test(`holding ${what} opens it and changes nothing`, async ({ page }) => {
      await settled(page, url)
      const tile = page.locator(selector).first()
      const line = tile.locator('.tile-state, .onnow-name').first()
      const before = await line.innerText({ timeout: 1500 }).catch(() => '')

      const { x, y } = await centre(page, selector)
      await press(page, x, y, 560)

      await expect(page.locator('.opened-panel')).toHaveCount(1)
      if (before) await expect(line).toHaveText(before)
    })
  }
})
