/* The gesture has two jobs and they must not collide: a tap still controls the
   device, a hold opens it and controls nothing. This checks both, because the
   failure mode is silent — a lamp that switches off on its way into its detail. */
import { chromium } from 'playwright'
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
await page.goto(BASE + '/?room=living&at=19:40', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)

const tile = page.locator('.tile.light').first()
const state = () => tile.locator('.tile-state').innerText()
const box = await tile.boundingBox()
const cx = box.x + box.width / 2, cy = box.y + box.height / 2

const before = await state()

// 1. a tap must still toggle
await page.mouse.click(cx, cy)
await page.waitForTimeout(600)
const afterTap = await state()

// back to where we started
await page.mouse.click(cx, cy)
await page.waitForTimeout(600)
const restored = await state()

// 2. a hold must open, and must NOT toggle
await page.mouse.move(cx, cy)
await page.mouse.down()
await page.waitForTimeout(520)
await page.mouse.up()
await page.waitForTimeout(700)
const opened = await page.locator('.opened-panel').count()
const afterHold = await page.locator('.opened-big').innerText()

console.log('tap toggles: ', before, '->', afterTap, afterTap !== before ? 'PASS' : 'FAIL')
console.log('tap restores:', restored === before ? 'PASS' : 'FAIL (' + restored + ')')
console.log('hold opens:  ', opened === 1 ? 'PASS' : 'FAIL')
console.log('hold did not toggle:', afterHold.startsWith(before.split('%')[0]) ? 'PASS (' + afterHold + ')' : 'FAIL (panel says ' + afterHold + ', tile was ' + before + ')')
await browser.close()
