// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Houses app (design/houses/, The app and B), and the panel inside it (src/inapp.ts), driven against the mock
 * brain as the house.
 *
 * Both halves need a page on the app's own dev origin, 5174, served for real from this machine: Chrome lets a page
 * frame a house on this machine only when that page really came from here, and a page the test runner fulfills
 * itself counts as the public internet. So one server here serves the built app (app/dist-houses, npm run
 * build:houses) and, at /stand-in, a stand-in for the app that plays its half of the handshake by hand; a second,
 * on 5175, is some other site. One file, run in order, because two servers cannot both have 5174 -- found 3 October,
 * when two files each started their own and CI ran them side by side.
 *
 * The mock speaks the move: K7Q4MPWR is the code that works, anything else is the brain's 410. */
import { expect, test, type Page } from '@playwright/test'
import { createServer, type Server } from 'node:http'
import { readFileSync, existsSync } from 'node:fs'
import { dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

test.describe.configure({ mode: 'serial' })

const APP = 'http://localhost:5174'
const ELSE = 'http://localhost:5175'
const DIST = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist-houses')
const TYPES: Record<string, string> = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json' }

/* The app's half, by hand: frame the panel as the app does, hand it a pass when it says it is ready, keep what it says. */
const standIn = (base: string, others: boolean) => `<!doctype html>
  <body style="margin:0"><iframe id="f" allow="local-network-access" src="${base}/?app=1&layout=wall&nav=top&at=19:40" style="border:0;width:390px;height:844px"></iframe>
  <script>
    window.said = []
    const f = document.getElementById('f')
    addEventListener('message', ev => {
      if (ev.source !== f.contentWindow) return
      window.said.push(ev.data.type)
      if (ev.data.type === 'houses:ready') f.contentWindow.postMessage({ type: 'houses:token', token: 'from-the-app', lan: null, name: 'Lake house', others: ${others} }, ev.origin)
    })
  </script>`

let servers: Server[] = []
test.beforeAll(() => {
  if (!existsSync(join(DIST, 'index.html'))) throw new Error('npm run build:houses first')
  const base = process.env.BASE || 'http://localhost:8399'
  const serve = (appToo: boolean) => createServer((req, res) => {
    const path = (req.url || '/').split('#')[0]
    if (!appToo || path.startsWith('/stand-in')) {
      res.writeHead(200, { 'Content-Type': 'text/html' })
      return res.end(standIn(base, path.includes('others')))
    }
    const file = join(DIST, path.split('?')[0])
    const real = path !== '/' && existsSync(file) && !file.endsWith('/') ? file : join(DIST, 'index.html')    // try_files {path} /index.html
    res.writeHead(200, { 'Content-Type': TYPES[extname(real)] ?? 'application/octet-stream' })
    res.end(readFileSync(real))
  })
  servers = [serve(true).listen(5174), serve(false).listen(5175)]
})
test.afterAll(() => { for (const s of servers) s.close() })

async function app(page: Page, origin: string, _base: string, others = false) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${origin}/stand-in${others ? '?others' : ''}`)
}

// ---- the app ------------------------------------------------------------------------------------

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1'

async function fresh(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${APP}/`)
  await page.evaluate(() => new Promise(r => { const q = indexedDB.deleteDatabase('houses'); q.onsuccess = q.onerror = q.onblocked = () => r(null) }))
}

test('a link from the house carries it in: named by the phone, then opened with its name as the switch', async ({ page }) => {
  await fresh(page)
  await page.goto(`${APP}/add#h=maple-court&c=K7Q4MPWR`)
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
  await page.goto(`${APP}/add#h=maple-court&c=K7Q4MPWR`)
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
  await page.getByLabel('The house’s web address').fill('maple-court.elyir.app')
  await page.getByLabel('The code').fill('AAAA BBBB')
  await expect(page.locator('.hs-error')).toContainText("isn't right")
  await page.getByLabel('The code').fill('k7q4-mpwr')
  await expect(page.getByRole('heading', { name: 'Added.' })).toBeVisible()
})

// ---- the panel inside it -------------------------------------------------------------------------

test('inside the app, the house is named where Connected was, and the name opens the houses', async ({ page, baseURL }) => {
  await app(page, APP, baseURL!, true)
  const frame = page.frameLocator('#f')
  const name = frame.locator('.house-switch')
  await expect(name).toContainText('Lake house')
  await expect(frame.locator('.topbar .link')).toHaveCount(0)
  await expect(name).toHaveClass(/others/)                         // another house wants somebody
  await name.click()
  await expect.poll(() => page.evaluate(() => (window as any).said)).toContain('houses:open')
})

test('the panel takes a pass only from the app', async ({ page, baseURL }) => {
  await app(page, ELSE, baseURL!)
  const frame = page.frameLocator('#f')
  await expect(frame.locator('.topbar')).toBeVisible()
  await page.waitForTimeout(1500)
  await expect(frame.locator('.house-switch')).toHaveCount(0)      // nothing taken, so no name and no switch
})

test('outside the app, nothing changes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/?layout=wall&nav=top&at=19:40')
  await expect(page.locator('.topbar .link')).toBeVisible()
  await expect(page.locator('.house-switch')).toHaveCount(0)
})
