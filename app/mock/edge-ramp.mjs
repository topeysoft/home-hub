/* Where on the way in does a card become crisp? Scroll in small steps, and each
   time report the card straddling the right edge: how much of it is visible
   against what it resolved to. The ramp should be done by about half. */
import { chromium } from 'playwright'
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
await page.goto(BASE + '/?layout=rail&at=19:40', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)
const rows = []
for (let s = 0; s <= 700; s += 35) {
  await page.evaluate((s) => {
    const rail = document.querySelector('.bento')
    rail.style.scrollSnapType = 'none'                          // snap would round every step to a card edge; a finger mid-swipe is between them
    rail.scrollLeft = s
  }, s)
  await page.waitForTimeout(80)                                 // scroll-driven animations resolve on the next frame, not in this tick
  const r = await page.evaluate(() => {
    const rail = document.querySelector('.bento')
    const rr = rail.getBoundingClientRect()
    for (const c of rail.children) {
      const b = c.getBoundingClientRect()
      if (b.left < rr.right && b.right > rr.right) {           // straddling the right edge: arriving
        const vis = (rr.right - b.left) / b.width, cs = getComputedStyle(c)
        return { vis, opacity: +cs.opacity, blur: cs.filter }
      }
    }
    return null
  })
  await page.waitForTimeout(60)
  if (r) rows.push(`  ${(r.vis * 100).toFixed(0).padStart(3)}% in  ->  opacity ${r.opacity.toFixed(2)}  ${r.blur}`)
}
console.log('arriving card, visible fraction -> resolved style\n' + [...new Set(rows)].join('\n'))
await browser.close()
