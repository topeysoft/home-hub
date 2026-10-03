// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Houses app (design/houses/, The app and B), driven against the mock brain as the house. The built app is
 * served here on its dev origin, 5174, from app/dist-houses (npm run build:houses), because Chrome only lets a
 * page on this machine frame a house on this machine when the page really came from here.
 *
 * The mock speaks the move: K7Q4MPWR is the code that works, anything else is the brain's 410. */
import { expect, test, type Page } from '@playwright/test'
import { createServer, type Server } from 'node:http'
import { readFileSync, existsSync } from 'node:fs'
import { dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const APP = 'http://localhost:5174'
const DIST = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist-houses')
const TYPES: Record<string, string> = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json' }

let server: Server
test.beforeAll(() => {
  if (!existsSync(join(DIST, 'index.html'))) throw new Error('npm run build:houses first')
  server = createServer((req, res) => {
    const path = (req.url || '/').split('?')[0].split('#')[0]
    const file = join(DIST, path)
    const real = path !== '/' && existsSync(file) ? file : join(DIST, 'index.html')     // try_files {path} /index.html
    res.writeHead(200, { 'Content-Type': TYPES[extname(real)] ?? 'application/octet-stream' })
    res.end(readFileSync(real))
  }).listen(5174)
})
test.afterAll(() => server?.close())

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1'

async function fresh(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${APP}/`)
  await page.evaluate(() => new Promise(r => { const q = indexedDB.deleteDatabase('houses'); q.onsuccess = q.onerror = q.onblocked = () => r(null) }))
}

test('a link from the house carries it in: named by the phone, then opened with its name as the switch', async ({ page }) => {
  await fresh(page)
  await page.goto(`${APP}/add#h=main-palace&c=K7Q4MPWR`)
  await expect(page.getByRole('heading', { name: 'Added.' })).toBeVisible()
  expect(new URL(page.url()).hash, 'the code is not kept in the address').toBe('')
  await page.getByRole('button', { name: 'Lake house' }).click()
  await page.getByRole('button', { name: 'Open Lake house' }).click()

  const house = page.frameLocator('.hs-frame')
  const name = house.locator('.house-switch')
  await expect(name).toContainText('Lake house')
  await expect(name, 'connected, with the pass the app handed over').toHaveClass(/\bup\b/)
  await name.click()
  const sheet = page.getByRole('dialog', { name: 'Houses' })
  await expect(sheet).toBeVisible()
  await expect(sheet.locator('.hs-row', { hasText: 'Lake house' })).toBeVisible()
  await expect(sheet.locator('.hs-row', { hasText: 'Add a house' })).toBeVisible()

  // and it is still there the next time the app opens
  await page.goto(`${APP}/`)
  await expect(page.frameLocator('.hs-frame').locator('.house-switch')).toContainText('Lake house')
})

test('on an iPhone in Safari nothing is added: the code is shown to carry to the Home Screen app', async ({ browser }) => {
  const ctx = await browser.newContext({ userAgent: IPHONE, viewport: { width: 390, height: 844 } })
  const page = await ctx.newPage()
  await page.goto(`${APP}/add#h=main-palace&c=K7Q4MPWR`)
  await expect(page.getByRole('heading', { name: 'Add Houses to your Home Screen.' })).toBeVisible()
  await expect(page.locator('.hs-carry .hs-code i:not(.gap)')).toHaveText(['K', '7', 'Q', '4', 'M', 'P', 'W', 'R'])
  const kept = await page.evaluate(() => new Promise(r => { const q = indexedDB.open('houses', 1); q.onsuccess = () => { const db = q.result; if (!db.objectStoreNames.contains('houses')) return r(0); const g = db.transaction('houses').objectStore('houses').count(); g.onsuccess = () => r(g.result) } }))
  expect(kept, 'nothing was added in Safari').toBe(0)
  await ctx.close()
})

test('the Home Screen app asks for the code, and a wrong one says so', async ({ page }) => {
  await fresh(page)
  await page.goto(`${APP}/add`)
  await expect(page.getByRole('heading', { name: 'Add a house' })).toBeVisible()
  await page.getByLabel('The house’s web address').fill('main-palace.elyir.app')
  await page.getByLabel('The code').fill('AAAA BBBB')
  await expect(page.locator('.hs-error')).toContainText("isn't right")
  await page.getByLabel('The code').fill('k7q4-mpwr')
  await expect(page.getByRole('heading', { name: 'Added.' })).toBeVisible()
})
