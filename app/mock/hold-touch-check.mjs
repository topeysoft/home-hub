/* The hold, with a finger rather than a mouse. A touch long-press is also the
   browser's own gesture, and the wall panel is a touch screen, so a mouse-only
   pass proves less than it looks like. Uses Chromium's touch input directly,
   which is the same path a real finger takes. Checks Home and a room. */
import { chromium, devices } from 'playwright'
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const browser = await chromium.launch()
const ctx = await browser.newContext({ ...devices['iPad Pro 11'], hasTouch: true })
const page = await ctx.newPage()
const cdp = await ctx.newCDPSession(page)

async function press(x, y, ms) {
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
  await page.waitForTimeout(ms)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
}

async function check(label, url, selector) {
  await page.goto(BASE + url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(900)
  const el = page.locator(selector).first()
  // a camera tile has no state line; without a short timeout this auto-waits 30s for one
  const state = async () => (await el.locator('.tile-state, .onnow-name').first().innerText({ timeout: 1500 }).catch(() => '')).trim()
  const before = await state()
  await el.scrollIntoViewIfNeeded()          // a finger cannot press what is below the fold
  await page.waitForTimeout(250)
  // measured immediately before the press: Home's layout shifts ~80px in the
  // first seconds as async blocks land above the cameras, so an earlier box is stale
  const b = await el.boundingBox()
  const x = b.x + b.width / 2, y = b.y + b.height / 2
  const hit = await page.evaluate(([x, y]) => { const e = document.elementFromPoint(x, y); return e ? e.className.toString().split(' ')[0] || e.tagName : 'nothing' }, [x, y])
  await press(x, y, 560)
  await page.waitForTimeout(700)
  const opened = await page.locator('.opened-panel').count()
  const after = await state()
  console.log(label.padEnd(26), 'opened:', opened === 1 ? 'PASS' : 'FAIL', ' unchanged:', before === after ? 'PASS' : `FAIL (${before} -> ${after})`, ' under finger:', hit)
  await page.locator('.opened-close').click().catch(() => {})
  await page.waitForTimeout(400)
}

await check('room, light tile', '/?room=living&at=19:40', '.tile.light')
await check('room, plain tile', '/?room=living&at=19:40', '.tile.plain')
await check('home (stack), camera', '/?layout=stack&at=19:40', '.tile.camera')
await check('home (stack), on-now chip', '/?layout=stack&at=19:40', '.onnow-chip')
await check('home (rail), card', '/?layout=rail&at=19:40', '.bento-card')
await browser.close()
