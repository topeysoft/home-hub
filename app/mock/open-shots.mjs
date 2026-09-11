/* Holding a card open, caught mid-flight. The settled frame proves the layout;
   the frames at 140ms and 260ms prove the home actually recedes and the content
   actually staggers, which a settled screenshot cannot tell you. */
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 })

await page.goto(BASE + '/?room=living&at=19:40', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)
await page.screenshot({ path: path.join(OUT, 'open-0-before.png') })

// hold the floor lamp: press, wait past the hold threshold, release
const card = page.locator('.tile.light').first()
const box = await card.boundingBox()
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
await page.mouse.down()
await page.waitForTimeout(470)          // past HOLD (420ms): the panel is on its way
await page.screenshot({ path: path.join(OUT, 'open-1-rising.png') })
await page.mouse.up()
await page.waitForTimeout(150)
await page.screenshot({ path: path.join(OUT, 'open-2-mid.png') })
await page.waitForTimeout(700)
await page.screenshot({ path: path.join(OUT, 'open-3-settled.png') })

// and the state it leaves behind
const shell = await page.evaluate(() => {
  const s = document.querySelector('.shell'), st = document.querySelector('.stage')
  return JSON.stringify({
    shellClass: s.className,
    stageTransform: getComputedStyle(st).transform,
    stageFilter: getComputedStyle(st).filter,
    tint: getComputedStyle(s).getPropertyValue('--open-tint').trim().slice(0, 48),
    panel: getComputedStyle(document.querySelector('.opened-panel')).transform,
  })
})
console.log(shell)
await browser.close()
