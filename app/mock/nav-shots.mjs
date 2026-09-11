/* The Top navigation and the rail sized as drawn. Pictures for the look, and
   the rail's card boxes as numbers, because "matches the artboard" is a claim
   about pixels: a tall card should come to 340, a stacked one to 196, on a 900-tall wall;
   a shorter screen scales the rows down rather than scrolling. */
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const KIOSK = { width: 1280, height: 800 }, PHONE = { width: 390, height: 844 }
const browser = await chromium.launch()

async function shot(name, url, size, act) {
  const page = await browser.newPage({ viewport: size, deviceScaleFactor: 1 })
  await page.goto(BASE + url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(900)
  if (act) await act(page)
  await page.screenshot({ path: path.join(OUT, name + '.png') })
  console.log(name)
  return page
}

// the rail's boxes, as numbers
const rail = await shot('bento-sized', '/?layout=rail&at=19:40', KIOSK)
console.log(await rail.evaluate(() => [...document.querySelectorAll('.bento > *')].map((c) => {
  const b = c.getBoundingClientRect(), kind = [...c.classList].find((k) => ['light', 'media', 'plain', 'camera', 'climate'].includes(k)) || '?'
  return `  ${kind.padEnd(8)} ${Math.round(b.width)}x${Math.round(b.height)} at x=${Math.round(b.left)}`
}).join('\n')))
await rail.close()

await shot('nav-top-home', '/?nav=top&at=19:40', KIOSK)
await (await shot('nav-top-rooms', '/?nav=top&at=19:40', KIOSK, async (p) => { await p.getByRole('button', { name: /^Rooms$/ }).click(); await p.waitForTimeout(500) })).close()
await (await shot('nav-top-cameras', '/?nav=top&at=19:40', KIOSK, async (p) => { await p.getByRole('button', { name: /^Cameras$/ }).click(); await p.waitForTimeout(500) })).close()
await (await shot('nav-top-phone', '/?nav=top&at=19:40', PHONE)).close()
await (await shot('look-sheet-nav', '/?sheet=look&at=19:40', KIOSK)).close()
await browser.close()
