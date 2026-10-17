// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Which room a thermostat keeps right, as design/thermostat/RoomsB.dc.html draws it (B, chosen 7 October).

   An Ecobee brings a sensor to other rooms, its own Home, Away and Sleep, and the air. The pane's Sensor
   row grew into a list of rooms -- its own sensors first, each room with its reading and a dot where
   somebody is -- between the modes and the fan, and the sentence under the number says when it set itself
   to Away. Nothing on the wall picks Away. This fails on purpose if the arrangement drifts from the board.

   The mock's thermostat is a plain one, so the brain's answer is rewritten into an Ecobee's rather than
   adding devices every other screen would then have to account for. */
import { expect, test, type Page } from '@playwright/test'

async function anEcobee(page: Page) {
  await page.route('**/home*', async (route) => {
    const res = await route.fetch()
    const home = await res.json()
    for (const r of home.rooms ?? []) for (const d of r.devices) {
      if (d.id === 't1') Object.assign(d.attrs, { own_sensors: 2, air: 'Good', comfort: 'away', comfort_since: Date.now() / 1000 - 3600 })
    }
    home.rooms.find((r: any) => r.id === 'bedroom')?.devices.push(
      { id: 'sensor.eco_bedroom', name: 'Bedroom', room_id: 'bedroom', capability: 'sensor.temperature', state: '70', attrs: { unit_of_measurement: '°F' } })
    await route.fulfill({ response: res, json: home })
  })
}

async function openThermostat(page: Page) {
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  for (let go = 0; go < 3; go++) {
    const tile = page.locator('.tile.climate').first()
    await expect(tile).toBeVisible()
    await page.waitForTimeout(600)
    const box = (await tile.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
    await page.mouse.down()
    await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10000 })
    await page.mouse.up()
    await page.waitForTimeout(700)
    if (await page.locator('.rig-climate').count()) return
    await page.keyboard.press('Escape')
    await expect(page.locator('.opened-panel')).toHaveCount(0, { timeout: 5000 })
    await page.waitForTimeout(400)
  }
  await expect(page.locator('.rig-climate')).toHaveCount(1)
}

test('the rooms it can feel sit between the modes and the fan, its own sensors first', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await anEcobee(page)
  await openThermostat(page)

  const rows = page.locator('.clim-keep-row')
  await expect(rows.first()).toContainText('Its own sensors')
  await expect(rows.first()).toHaveClass(/\bon\b/)
  await expect(page.locator('.clim-keep-row', { hasText: 'Bedroom' })).toContainText('70°')
  await expect(page.locator('.clim-keep-row', { hasText: 'Living room' }).locator('.clim-keep-here.in')).toHaveCount(1)   // the mock's living room has motion
  await expect(page.locator('.clim-keep-row', { hasText: 'Bedroom' }).locator('.clim-keep-here.in')).toHaveCount(0)

  const at = await page.evaluate(() => {
    const r = (s: string) => document.querySelector(s)!.getBoundingClientRect()
    const fan = [...document.querySelectorAll('.rig-side .rig-row')].find(e => e.textContent!.includes('Fan'))!.getBoundingClientRect()
    return { modes: r('.rig-modes'), keep: r('.clim-keep'), fan, rig: r('.pane-rig'), page: document.scrollingElement!.scrollHeight }
  })
  expect(at.keep.top, 'the list comes after the modes').toBeGreaterThan(at.modes.bottom)
  expect(at.fan.top, 'and before the fan').toBeGreaterThan(at.keep.bottom)
  expect(at.fan.bottom, 'all of it inside the instrument').toBeLessThanOrEqual(at.rig.bottom)
  expect(at.page, 'one screen on a wall, nothing to scroll').toBeLessThanOrEqual(900)
})

test('away is said under the number, and the air beside the humidity -- with nothing to pick', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await anEcobee(page)
  await openThermostat(page)
  // "yesterday at" once the clock has passed midnight since the mock's event: the suite runs at any hour
  await expect(page.locator('.pane-why')).toContainText(/The thermostat set itself to Away (yesterday )?at/)
  await expect(page.locator('.opened-facts')).toContainText('Good')
  await expect(page.locator('.opened-facts')).toContainText(/air/i)
  await expect(page.locator('.pane-rig').getByText('Away', { exact: true })).toHaveCount(0)
})
