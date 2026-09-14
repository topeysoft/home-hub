/* The look sheet, and proof that picking in it actually changes the panel. */
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'shots')
const BASE = process.env.BASE || `http://localhost:${process.env.PORT || 8399}`
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 })

await page.goto(BASE + '/?sheet=look&at=19:40', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)
await page.screenshot({ path: path.join(OUT, 'look-sheet.png') })
console.log('look-sheet')

// pick Nightfall: one tap, and the panel behind is made of glass. Scoped to the
// card, because once the house IS on Nightfall the door in the side list says so
// too and a bare getByText matches both.
await page.locator('.look-feel-name', { hasText: /^Nightfall/ }).click()
await page.waitForTimeout(600)
await page.screenshot({ path: path.join(OUT, 'look-sheet-picked.png') })
console.log('look-sheet-picked')

// and the four dials are still all there, one row down
await page.getByText('Customise this look', { exact: true }).click()
await page.waitForTimeout(400)
await page.screenshot({ path: path.join(OUT, 'look-sheet-custom.png'), fullPage: true })
console.log('look-sheet-custom')

await page.getByText('Pastel', { exact: true }).click()
await page.waitForTimeout(600)
await page.screenshot({ path: path.join(OUT, 'look-sheet-adjusted.png') })
console.log('look-sheet-adjusted (should say "Nightfall, adjusted")')

await page.keyboard.press('Escape').catch(() => {})
await page.goto(BASE + '/?at=13:00&wx=sunny', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)
await page.screenshot({ path: path.join(OUT, 'look-applied.png') })
console.log('look-applied (should be glass + Pastel, arranged for this screen, with no URL params saying so)')

// the same house on a phone: same feel, laid out for what it is on
const phone = await browser.newPage({ viewport: { width: 414, height: 896 }, deviceScaleFactor: 1 })
await phone.goto(BASE + '/?sheet=look&at=19:40', { waitUntil: 'networkidle' })
await phone.waitForTimeout(900)
await phone.screenshot({ path: path.join(OUT, 'look-sheet-phone.png') })
console.log('look-sheet-phone')

await browser.close()
