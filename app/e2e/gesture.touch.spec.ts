/* The same gesture, made with a finger. A touch long-press is also the browser's own gesture, and
   the wall panel is a touch screen, so a mouse-only pass proves less than it looks like. This
   dispatches touch through CDP, the path a real finger takes. */
import { expect, test, type Page } from '@playwright/test'

const ROOM = '/?room=living&at=19:40'

/* Stop the page's clock, so a press can be measured out by hand instead of slept through.
 *
 * `install` looks like it does this and does not: it swaps the timer functions for fakes and leaves
 * the clock running, so `runFor` only ADDS to a wall clock still turning underneath. Measured -- a
 * 420ms timer set under a bare `install`, advanced by 150 and then left alone, goes off by itself
 * 1.5s later. `pauseAt` is the one that stops time, and it takes the PAGE's clock, not the runner's:
 * the two drift, and it refuses an instant in the past.
 *
 * It goes here, at the end of settling, rather than inside the press. Pausing jumps the clock
 * forward to the instant named, which fires whatever fell due in between -- and that is a real
 * event: a two second jump taken mid-test moved a tile's state out from under a reading the test
 * had already taken. Jumping before anything is measured means whatever lands, lands first, and
 * the test then measures the room it is actually looking at. */
async function freeze(page: Page) {
  await page.clock.install()
  /* As small a step as will still land ahead of the page: pausing JUMPS to the instant named and
     fires everything due in between, and a jump is not free -- at two seconds it expired the line
     on a card mid-test and the test read a room that had moved. The ladder is for a round trip that
     stalls past the cushion, which is the only way pauseAt can refuse. */
  for (const cushion of [100, 250, 600]) {
    try { return await page.clock.pauseAt(await page.evaluate(() => Date.now()) + cushion) }
    catch (e) { if (!/past/i.test(String(e))) throw e }
  }
  throw new Error('the page clock kept outrunning the cushion, so the press cannot be timed')
}

async function settled(page: Page, url: string) {
  await page.goto(url, { waitUntil: 'networkidle' })
  await expect(page.locator('.tile').first()).toBeVisible()
  await page.waitForTimeout(700)
  await freeze(page)
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

/* The finger is held for exactly this long: the clock was stopped by `settled`, so this advances
   it by hand and hands it back the moment the touch lifts. Sleeping here instead means betting
   140ms of headroom against HOLD in hold.ts on a machine running six workers, and that bet was
   being lost. See the note over `freeze` for why it is stopped where it is. */
async function press(page: Page, x: number, y: number, ms: number) {
  const cdp = await page.context().newCDPSession(page)
  try {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    await page.clock.runFor(ms)
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  } finally {
    await page.clock.resume()
    await cdp.detach()
  }
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
