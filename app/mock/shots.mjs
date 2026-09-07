/* Every screen a person will see, as PNGs, against the mock brain: `npm run mock` in one terminal, `npm run shots` in
   another. Writes mock/shots/<name>.png. Needs Playwright once: `npx playwright install chromium`.
   SHOTS=kiosk-home,phone-room limits the run; BASE points at another panel (a real hub works too). */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || 'http://localhost:8399'
const SIZES = { kiosk: [1280, 800], wall: [1920, 1080], tablet: [820, 1180], phone: [390, 844] }
const SCREENS = [
  ['kiosk-home', 'kiosk', '/?at=19:40'],
  ['kiosk-home-day', 'kiosk', '/?at=13:00&wx=sunny'],
  ['kiosk-home-rain', 'kiosk', '/?at=23:10&wx=rainy'],
  ['kiosk-home-tall', 'kiosk', '/?at=19:40', [1280, 1600]],
  ['kiosk-room', 'kiosk', '/?room=living&at=19:40', [1280, 1000]],
  ['kiosk-room-3col', 'kiosk', '/?room=living&at=19:40', [1024, 1000]],
  ['kiosk-kitchen', 'kiosk', '/?room=kitchen&at=19:40'],
  ['kiosk-new-devices', 'kiosk', '/?room=unassigned&at=19:40'],
  ['kiosk-empty-room', 'kiosk', '/?room=bath&at=19:40'],
  ['kiosk-rest', 'kiosk', '/?rest=1&at=22:00'],
  ['kiosk-rest-day', 'kiosk', '/?rest=1&at=15:00'],
  ['sheet-add', 'kiosk', '/?sheet=add&at=19:40'],
  ['sheet-routines', 'kiosk', '/?sheet=routines&at=19:40'],
  ['sheet-why', 'kiosk', '/?sheet=why&room=living&at=19:40'],
  ['sheet-location', 'kiosk', '/?sheet=location&at=19:40'],
  ['sheet-code', 'kiosk', '/?sheet=code&at=19:40'],
  ['setup-welcome', 'kiosk', '/?setup=1&page=welcome&at=13:00'],
  ['setup-rooms', 'kiosk', '/?setup=1&page=rooms&at=13:00'],
  ['setup-devices', 'kiosk', '/?setup=1&page=devices&at=13:00'],
  ['setup-done', 'kiosk', '/?setup=1&page=done&at=13:00', [1280, 1000]],
  ['sheet-hub', 'kiosk', '/?sheet=hub&at=19:40'],
  ['wall-home', 'wall', '/?at=19:40'],
  ['tablet-home', 'tablet', '/?at=19:40'],
  ['phone-home', 'phone', '/?at=19:40', [390, 1400]],
  ['phone-room', 'phone', '/?room=living&at=19:40', [390, 1900]],
  ['phone-kitchen', 'phone', '/?room=kitchen&at=19:40', [390, 1100]],
  ['phone-sheet-add', 'phone', '/?sheet=add&at=19:40'],
  ['phone-setup-rooms', 'phone', '/?setup=1&page=rooms&at=13:00'],
]

const only = process.env.SHOTS ? new Set(process.env.SHOTS.split(',')) : null
mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch()
for (const [name, size, url, wh] of SCREENS) {
  if (only && !only.has(name)) continue
  const [width, height] = wh ?? SIZES[size]
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  await page.goto(BASE + url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)                       // sheets and the sky settle
  await page.screenshot({ path: path.join(OUT, `${name}.png`) })
  await ctx.close()
  console.log(name)
}
await browser.close()
