/* Where the rail's first card sits, against the rail's own left edge, and
   whether the row has scrolled on its own by the time anyone looks. */
import { chromium } from 'playwright'
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1280, height: 800 } })
await p.goto(BASE + '/?layout=rail&at=19:40', { waitUntil: 'networkidle' })
for (const wait of [300, 1500]) {
  await p.waitForTimeout(wait)
  console.log(await p.evaluate((wait) => {
    const r = document.querySelector('.bento'), f = r.firstElementChild, fb = f.getBoundingClientRect()
    return `after ${wait}ms: rail left=${Math.round(r.getBoundingClientRect().left)} scrollLeft=${r.scrollLeft} first=${f.className.split(' ').find((k) => ['light', 'media', 'plain', 'camera', 'climate'].includes(k))} x=${Math.round(fb.left)} ${Math.round(fb.width)}x${Math.round(fb.height)} children=${r.children.length}`
  }, wait))
}
await b.close()
