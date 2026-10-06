/* The Home states that need the mock's knobs rather than a URL parameter: a
   phone asking to join, and a Needs a look list with acted-on lines. Both are
   worth re-checking whenever the card tokens move, because both sit among cards
   that follow the sky while they deliberately do not.

     ASK=1 LOCKED=1 NEEDSLOOK=1 PORT=8401 npm run mock
     PORT=8401 node mock/state-shots.mjs
*/
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const SHOTS = [
  ['ask-midday', '/?at=13:00&wx=sunny&layout=rail'],
  ['ask-night', '/?at=23:30&wx=clear-night&layout=rail'],
  ['notes-rail-midday', '/?at=13:00&wx=sunny&layout=rail'],
  ['notes-stack-night', '/?at=23:30&wx=clear-night&layout=stack'],
]

const browser = await chromium.launch()
for (const [name, url] of SHOTS) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 })
  await page.goto(BASE + url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  await page.screenshot({ path: path.join(OUT, name + '.png') })
  await page.close()
  console.log(name)
}
await browser.close()
