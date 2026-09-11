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

// pick Rail, then Pastel, then close: the panel behind should have changed
await page.getByText('Rail', { exact: true }).click()
await page.waitForTimeout(500)
await page.getByText('Pastel', { exact: true }).click()
await page.waitForTimeout(500)
await page.screenshot({ path: path.join(OUT, 'look-sheet-picked.png') })
console.log('look-sheet-picked')

await page.keyboard.press('Escape').catch(() => {})
await page.goto(BASE + '/?at=13:00&wx=sunny', { waitUntil: 'networkidle' })
await page.waitForTimeout(900)
await page.screenshot({ path: path.join(OUT, 'look-applied.png') })
console.log('look-applied (should be Rail + Pastel, with no URL params saying so)')

await browser.close()
