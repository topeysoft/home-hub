// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The panel inside the Houses app (design/houses/, B; src/inapp.ts). A stand-in for the app is served on the app's
 * own dev origin, frames the panel the way the app does (?app=1), and plays the app's half: it waits for the panel
 * to say it is ready, hands it a pass and the house's name, and listens for the tap on that name. The panel must
 * take the pass from the app and nobody else, show the house's name where Connected was, and send the tap back. */
import { expect, test, type Page } from '@playwright/test'
import { createServer, type Server } from 'node:http'

const APP = 'http://localhost:5174'
const ELSE = 'http://localhost:5175'

/* The app's half, served from a real local server: a page the test runner fulfills itself counts as the public
   internet to Chrome's local-network checks, and would never be allowed to frame a house on this machine. */
const page_ = (base: string, others: boolean) => `<!doctype html>
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
let base = ''
test.beforeAll(async () => {
  base = process.env.BASE || 'http://localhost:8399'
  servers = [5174, 5175].map(port => createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html' })
    res.end(page_(base, req.url?.includes('others') ?? false))
  }).listen(port))
})
test.afterAll(() => { for (const s of servers) s.close() })

async function app(page: Page, origin: string, _base: string, others = false) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${origin}/${others ? '?others' : ''}`)
}

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
