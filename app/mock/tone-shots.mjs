/* The tone engine and the two layouts, at several hours and skies, so a change to
   tone.ts or RailView.vue can be looked at rather than reasoned about.
   `npm run mock` in one terminal, `node mock/tone-shots.mjs` in another.
   PORT is the mock's port; BASE points somewhere else entirely. */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const KIOSK = { width: 1280, height: 800 }
const PHONE = { width: 390, height: 844 }
const SHOTS = [
  // the tone, against the sky it is derived from
  ['tone-night', '/?at=23:30&wx=clear-night', KIOSK],
  ['tone-dusk', '/?at=19:40', KIOSK],
  ['tone-midday-sun', '/?at=13:00&wx=sunny', KIOSK],
  ['tone-midday-storm', '/?at=13:00&wx=pouring', KIOSK],
  ['tone-midday-pastel', '/?at=13:00&wx=sunny&tone=pastel', KIOSK],
  ['tone-night-pastel', '/?at=23:30&wx=clear-night&tone=pastel', KIOSK],
  ['tone-room-midday', '/?room=living&at=13:00&wx=sunny', KIOSK],
  // the two layouts, same house, same hour
  ['stack-dusk', '/?layout=stack&at=19:40', KIOSK],
  ['rail-dusk', '/?layout=rail&at=19:40', KIOSK],
  ['rail-midday', '/?layout=rail&at=13:00&wx=sunny', KIOSK],
  ['rail-phone', '/?layout=rail&at=19:40', PHONE],
  ['stack-phone', '/?layout=stack&at=19:40', PHONE],
]

mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch()
for (const [name, url, size] of SHOTS) {
  const page = await browser.newPage({ viewport: size, deviceScaleFactor: 1 })
  await page.goto(BASE + url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(900)                       // the sky settles, the cards take their colour
  await page.screenshot({ path: path.join(OUT, name + '.png') })
  await page.close()
  console.log(name)
}
await browser.close()
