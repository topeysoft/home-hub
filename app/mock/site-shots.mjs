/* The pictures on the front page (site/, hub.elyir.com), taken from the built panel on the pretend house with made-up
   names (NAMES=plain), so the page never shows somebody else's show or brand. `npm run build`, then
   `npm run site-shots`. Writes site/shots/; run it again whenever the panel changes how it looks. */
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(HERE, '..', '..', 'site', 'shots')
const PORT = process.env.PORT || '8475'
const BASE = `http://localhost:${PORT}`
const SHOTS = [
  ['wall-evening', [1440, 900], 'dark', '/?at=19:40'],
  ['wall-room', [1440, 900], 'dark', '/?room=living&at=19:40'],
  ['phone-home-dark', [390, 844], 'dark', '/?at=19:40'],
  ['phone-home-light', [390, 844], 'light', '/?at=13:00&wx=sunny'],
]

const mock = spawn(process.execPath, [path.join(HERE, 'brain.mjs')], { env: { ...process.env, PORT, NAMES: 'plain' }, stdio: 'ignore' })
try {
  for (let i = 0; i < 50; i++) {
    try { if ((await fetch(BASE)).ok) break } catch {}
    await new Promise((r) => setTimeout(r, 100))
  }
  const browser = await chromium.launch()
  for (const [name, [width, height], colorScheme, query] of SHOTS) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2, colorScheme })
    await page.goto(BASE + query, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)   // the sky and the cards settle in; a screenshot is slower than none of this
    await page.screenshot({ path: path.join(OUT, `${name}.jpg`), type: 'jpeg', quality: 80 })
    await page.close()
    console.log(name)
  }
  await browser.close()
} finally {
  mock.kill()
}
