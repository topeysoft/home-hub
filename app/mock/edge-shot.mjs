/* The rail's edges: scroll it partway so a card is leaving on the left and
   another arriving on the right, then read what each card actually resolved to.
   A screenshot shows the look; the numbers prove the ramp runs the right way. */
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 })
await page.goto(BASE + '/?layout=rail&at=19:40', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)

const report = async (tag) => {
  const rows = await page.evaluate(() => {
    const rail = document.querySelector('.bento'), r = rail.getBoundingClientRect()
    return [...rail.children].map((c) => {
      const b = c.getBoundingClientRect(), cs = getComputedStyle(c)
      const visible = Math.max(0, Math.min(b.right, r.right) - Math.max(b.left, r.left)) / b.width
      return `${(c.className.split(' ').find((k) => k !== 'bento-card' && k !== 'tile') || 'card').padEnd(8)} visible ${(visible * 100).toFixed(0).padStart(3)}%  opacity ${Number(cs.opacity).toFixed(2)}  ${cs.filter}`
    })
  })
  console.log(`\n${tag}\n  ` + rows.join('\n  '))
}

await report('at rest (scrollLeft 0)')
await page.screenshot({ path: path.join(OUT, 'edge-0-rest.png') })

// sweep so one card straddles the left edge and one the right
await page.evaluate(() => { document.querySelector('.bento').scrollLeft = 300 })
await page.waitForTimeout(400)
await report('scrolled 300px')
await page.screenshot({ path: path.join(OUT, 'edge-1-mid.png') })

console.log('\nscroll-driven animations supported by this browser:', await page.evaluate(() => CSS.supports('animation-timeline: view()')))
await browser.close()
