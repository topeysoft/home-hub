/* What a face costs, in frames rather than in opinions.
 *
 * Drives one rail swipe -- 650ms of travel at 1280x800, the wall panel's own size -- and records
 * the gap between presented frames under each face. `npm run mock` in one terminal, `npm run cost`
 * in another. BASE points somewhere else, and that is the point of the thing: run it against a real
 * hub on the host you actually mean, because nothing on a laptop stands in for a Pi's fill rate.
 *
 *   BASE=http://hub.local node mock/cost.mjs
 *
 * Headless Chromium rasterises in software, which is the nearest thing to a weak GPU available
 * without one, and is why the numbers below are worth anything at all. HEADED=1 uses the real GPU
 * instead; it is noisier and wants more than one run.
 *
 * What to look at: `>16.7ms` is frames that missed 60fps and `>33.4ms` is frames that missed 30.
 * `frosted` is how many surfaces on screen are painting a backdrop-filter, which is the load itself
 * -- and it is the same under both faces, because paper already frosts every tile. The difference
 * between the faces is the radius, not the count.
 */
import { chromium } from 'playwright'

const BASE = process.env.BASE || 'http://localhost:8399'
const RUNS = Number(process.env.RUNS || 3)
const TRAVEL = 650                                        // the rail's own 650ms, from design/nightfall
const FACES = (process.env.FACES || 'paper,glass').split(',')

const browser = await chromium.launch(process.env.HEADED ? { headless: false } : {})

async function swipe(face) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, timezoneId: 'America/Chicago', locale: 'en-US' })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/?at=19:40&face=${face}&nav=top&layout=rail`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1600)                         // past the row's own arrival, which is not what is being measured

  const out = await page.evaluate(async (travel) => {
    const row = document.querySelector('.bento')
    const card = row?.querySelector('.bento-card')
    if (!row || !card) return null
    const dist = card.getBoundingClientRect().width + 18  // one card and the row's gap

    /* Snapping off for the duration: a snap would fight the scroll being driven here and what came
       back would be the argument rather than the cost. */
    const snap = row.style.scrollSnapType
    row.style.scrollSnapType = 'none'
    row.scrollLeft = 0

    const frames = []
    await new Promise((done) => {
      let first = 0, last = 0
      const step = (t) => {
        if (!first) { first = t; last = t } else { frames.push(t - last); last = t }
        const k = Math.min((t - first) / travel, 1)
        row.scrollLeft = dist * (1 - (1 - k) ** 3)        // the same ease-out a finger leaves behind
        if (k < 1) requestAnimationFrame(step); else done()
      }
      requestAnimationFrame(step)
    })
    row.style.scrollSnapType = snap

    /* how much frosted surface was on screen while that happened, which is the load */
    let frosted = 0
    for (const el of document.querySelectorAll('*')) {
      const cs = getComputedStyle(el)
      const bf = cs.getPropertyValue('backdrop-filter') || cs.getPropertyValue('-webkit-backdrop-filter')
      if (!bf || bf === 'none') continue
      const r = el.getBoundingClientRect()
      if (r.width && r.height && r.right > 0 && r.left < innerWidth && r.bottom > 0 && r.top < innerHeight) frosted++
    }

    const sorted = [...frames].sort((a, b) => a - b)
    return {
      n: frames.length, frosted,
      median: sorted[Math.floor(sorted.length / 2)],
      p95: sorted[Math.floor(sorted.length * 0.95)],
      worst: sorted[sorted.length - 1],
      over16: frames.filter((f) => f > 16.7).length,
      over33: frames.filter((f) => f > 33.4).length,
    }
  }, TRAVEL)

  await ctx.close()
  if (!out) throw new Error('no rail on screen: this wants layout=rail with something on in the house')
  return out
}

const mid = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)]

console.log(`one rail swipe, ${TRAVEL}ms of travel, 1280x800, best of ${RUNS} — ${BASE}`)
console.log('face    frames  median     p95   worst   >16.7ms  >33.4ms   frosted')
for (const face of FACES) {
  const runs = []
  for (let i = 0; i < RUNS; i++) runs.push(await swipe(face))
  const r = runs.reduce((a, b) => (b.over33 < a.over33 ? b : a))          // the kindest run, so a stray frame is not the story
  console.log(
    `${face.padEnd(7)} ${String(mid(runs.map((x) => x.n))).padStart(5)}  ${r.median.toFixed(1).padStart(6)}  ${r.p95.toFixed(1).padStart(6)}`
    + ` ${r.worst.toFixed(1).padStart(7)} ${String(r.over16).padStart(9)} ${String(r.over33).padStart(8)} ${String(r.frosted).padStart(9)}`,
  )
}
await browser.close()
