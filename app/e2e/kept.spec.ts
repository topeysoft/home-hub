// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Nothing vanishes under the finger that touched it (AGENTS.md section 4), asked of the row on Home.
 *
 * A card in the row stands for something that is on, so turning it off could take it out -- and
 * whatever slid into its place took the second tap meant for it, turning on something nobody asked
 * for. The card keeps its place, drained, and is the undo. These tap a card and then ask the browser
 * what is under the same point, because a list of which cards exist would pass with every one of
 * them in the wrong place.
 *
 * The real hub answers a tap by pushing the device back down the stream; the mock does not, so the
 * answer is spoken here, a beat later, the way the house would say it.
 */
import { expect, test, type Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

type Dev = { id: string; name: string; state: string; capability: string }
let speak: (m: object) => void
let house: Dev[]

async function home(page: Page, playing: string[] = [], layout = 'layout=rail&nav=top') {
  if (playing.length) await page.route('**/home', async r => {
    const h = await (await r.fetch()).json()
    for (const d of h.rooms.flatMap((x: { devices: Dev[] }) => x.devices)) if (playing.includes(d.id)) d.state = 'playing'
    await r.fulfill({ json: h })
  })
  await page.routeWebSocket('**/stream', ws => { ws.connectToServer(); speak = m => ws.send(JSON.stringify(m)) })
  await page.goto(`/?${layout}&at=19:40`, { waitUntil: 'networkidle' })
  house = (await (await page.request.get('/home')).json()).rooms.flatMap((r: { devices: Dev[] }) => r.devices)
  await expect(page.locator('.bento, .onnow').first()).toBeVisible()
  await page.waitForTimeout(1500)                 // past the row's arrival
}
const tell = (id: string, state: string) => speak({ type: 'device', device: { ...house.find(d => d.id === id)!, state } })
const nameAt = (page: Page, at: { x: number; y: number }) => page.evaluate(({ x, y }) =>
  document.elementFromPoint(x, y)?.closest('.bento-card')?.querySelector('.tile-name')?.textContent?.trim() ?? null, at)
async function spot(page: Page, name: string) {
  const r = (await page.locator('.bento-card', { hasText: name }).first().boundingBox())!
  return { x: r.x + r.width / 2, y: r.y + Math.min(40, r.height / 2) }
}

test('a light turned off from its card is still there, and the next tap turns it back on', async ({ page }) => {
  await home(page)
  const at = await spot(page, 'Ceiling light')
  await page.mouse.click(at.x, at.y)
  tell(house.find(d => d.name === 'Ceiling light')!.id, 'off')
  await page.waitForTimeout(800)
  expect(await nameAt(page, at)).toBe('Ceiling light')
  await expect(page.locator('.bento-card.kept', { hasText: 'Ceiling light' })).toHaveCount(1)

  await page.mouse.click(at.x, at.y)
  tell(house.find(d => d.name === 'Ceiling light')!.id, 'on')
  await page.waitForTimeout(800)
  expect(await nameAt(page, at)).toBe('Ceiling light')
  await expect(page.locator('.bento-card.kept')).toHaveCount(0)
})

/* The tall first card belongs to a speaker. It was chosen afresh on every change -- the first one
   playing -- so pausing the TV while the Sonos played put the Sonos where the TV had been. */
test('pausing the speaker in the tall card does not hand its place to another one that is playing', async ({ page }) => {
  await home(page, ['s1'])                        // the Sonos is playing too, further along the row
  await expect(page.locator('.bento-card', { hasText: 'Blue in Green' })).toHaveCount(1)
  const at = await spot(page, 'TV')
  await page.locator('.bento-card', { hasText: 'TV' }).first().getByLabel('Pause').click()
  tell('m1', 'paused')
  await page.waitForTimeout(800)
  expect(await nameAt(page, at)).toBe('TV')
  expect(await page.locator('.bento-card').first().locator('.tile-name').innerText()).toContain('TV')
})

/* The same, on Stack's row of chips, which keeps its own list the same way and had the same hole. */
test('a chip turned off and back on stays where it was on the Stack home', async ({ page }) => {
  await home(page, [], 'layout=stack&nav=side')
  const chip = page.locator('.onnow-chip', { hasText: 'Ceiling light' })
  await page.waitForTimeout(1000)                 // Stack's page settles later than the row does
  const r = (await chip.boundingBox())!, at = { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  const here = () => page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('.onnow-chip')?.querySelector('.onnow-name')?.textContent?.trim(), at)
  const id = house.find(d => d.name === 'Ceiling light')!.id
  await page.mouse.click(at.x, at.y); tell(id, 'off'); await page.waitForTimeout(800)
  expect(await here()).toBe('Ceiling light')
  await page.mouse.click(at.x, at.y); tell(id, 'on'); await page.waitForTimeout(800)
  expect(await here()).toBe('Ceiling light')
  await expect(page.locator('.onnow-chip.kept')).toHaveCount(0)
})
