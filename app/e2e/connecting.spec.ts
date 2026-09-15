/* A camera whose picture is still on its way -- full screen, and in the sheet a hold opens on Home.
 *
 * The still is instant and a stream is not. `live.ts` gives an attempt WAIT = 12s before giving up on
 * it, and the viewer runs its two ways one after the other, so a camera that is simply off leaves
 * somebody looking at a motionless photograph for up to twenty-four seconds. What is under test is
 * that the screen says so for all of it -- and says something DIFFERENT once the second way begins,
 * because a label that reads the same at second 2 and at second 23 is how a screen that is working
 * comes to look like a screen that is stuck.
 *
 * The waits are faked rather than served: the mock destroys the WebRTC socket at once, so the first
 * way fails immediately and the second can be held open by stalling its stream. That buys the whole
 * progression in a second instead of twenty-four.
 */
import { expect, test, type Page } from '@playwright/test'

const WALL = '/?face=glass&layout=wall&nav=top&at=19:40'

/** Open the first camera with its moving picture hanging rather than refusing. */
async function watching(page: Page, { webrtc = true } = {}) {
  if (!webrtc) await page.addInitScript(() => { delete (window as any).RTCPeerConnection })
  await page.route('**/devices/**/stream*', () => { /* never fulfilled: the picture is on its way and never arrives */ })
  await page.goto(WALL, { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)
  await page.locator('.tile.camera').first().click()
  await expect(page.locator('.viewer-frame')).toBeVisible()
}

test('a picture on its way says so, rather than sitting there looking broken', async ({ page }) => {
  await watching(page, { webrtc: false })
  const frame = page.locator('.viewer-frame')
  await expect(frame).toHaveClass(/connecting/)
  await expect(page.locator('.viewer-live')).toHaveText(/Connecting/i)

  // and the frame is visibly working: a hairline travelling the top edge, not on the picture itself
  const bar = await frame.evaluate((el) => {
    const cs = getComputedStyle(el, '::after')
    return { height: cs.height, animation: cs.animationName, display: cs.display }
  })
  expect(bar.display, 'no bar at all').not.toBe('none')
  expect(bar.animation, 'the bar is not moving').toBe('viewer-connecting')
  expect(parseFloat(bar.height), 'the bar is not a hairline').toBeLessThan(5)
})

test('the second way says it is the second way', async ({ page }) => {
  /* The one thing that separates second 2 from second 23. The mock destroys the WebRTC socket, so the
     first way fails at once and the fallback starts; its stream is stalled, so this is where it sits. */
  await watching(page)
  await expect(page.locator('.viewer-live')).toHaveText(/Still trying/i)
  await expect(page.locator('.viewer-frame')).toHaveClass(/connecting/)
})

test('a camera that is simply not answering says that instead', async ({ page }) => {
  /* Both ways refused rather than hung: the viewer stops trying, and the chip goes back to telling
     the truth about the still underneath rather than promising a picture that is not coming. */
  await page.goto(WALL, { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)
  await page.locator('.tile.camera').first().click()
  await expect(page.locator('.viewer-frame')).toBeVisible()
  await expect(page.locator('.viewer-frame')).not.toHaveClass(/connecting/, { timeout: 8000 })
  await expect(page.locator('.viewer-live')).not.toHaveText(/Connecting|Still trying/i)
})

test.describe('asked not to move', () => {
  test.use({ reducedMotion: 'reduce' })

  test('the bar goes rather than freezing, and the words carry it', async ({ page }) => {
    /* A bar stopped at its start is worse than no bar: it is a second motionless object pretending to
       be busy, on a screen whose whole problem is looking motionless. */
    await watching(page, { webrtc: false })
    const bar = await page.locator('.viewer-frame').evaluate((el) => getComputedStyle(el, '::after').display)
    expect(bar, 'a frozen bar was left on the screen').toBe('none')
    await expect(page.locator('.viewer-live')).toHaveText(/Connecting/i)
  })
})

/* The sheet on Home, which is where this was reported from. It opens on a hold and wakes the camera
   after SETTLE, so the wait starts a moment later than the viewer's and is otherwise the same. */
test.describe('the sheet a hold opens', () => {
  async function held(page: Page) {
    await page.route('**/devices/**/stream*', () => {})
    await page.goto(WALL, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    const tile = page.locator('.tile.camera').first()
    const box = (await tile.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.waitForTimeout(600)      // past HOLD = 420ms
    await page.mouse.up()
    await expect(page.locator('.rig-still')).toBeVisible()
    await page.waitForTimeout(1400)     // past SETTLE = 800ms, so the camera has been asked
  }

  test('says it is connecting, in words and in a moving hairline', async ({ page }) => {
    await held(page)
    await expect(page.locator('.rig-still')).toHaveClass(/connecting/)
    await expect(page.locator('.rig-still-tag')).toHaveText(/Connecting/i)
    const bar = await page.locator('.rig-still').evaluate((el) => {
      const cs = getComputedStyle(el, '::after')
      return { display: cs.display, animation: cs.animationName }
    })
    expect(bar.display, 'the sheet has no bar').not.toBe('none')
    expect(bar.animation, 'the sheet bar is not moving').toBe('viewer-connecting')
  })

  test('still says how old the picture is, because waiting does not freshen it', async ({ page }) => {
    await held(page)
    await expect(page.locator('.rig-still-tag')).toHaveText(/Connecting ·/)
  })
})
