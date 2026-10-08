// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The end of an add that brought several things, as design/arrived/GuessC.dc.html draws it (C, chosen
   8 October).

   Reported from a real house: an Ecobee paired over HomeKit said Added. and offered Put them in rooms,
   which dropped a person into New devices with nothing marking what had just come in. Now the end of the
   add asks right there, a row a thing: the sensor the Ecobee app called Bedroom is already in the
   Bedroom, with Change beside it, and only the thermostat is asked. This fails on purpose if it drifts.

   The mock has no HomeKit, so the pairing is staged: a found thing, its code form, an entry, and the
   house's answer growing the four parts a thermostat and its sensor arrive as. */
import { expect, test, type Page } from '@playwright/test'

const part = (id: string, capability: string, hw: string, hw_name: string, name: string) =>
  ({ id, name, room_id: 'unassigned', capability, state: capability === 'climate' ? 'cool' : '70', attrs: {}, hw, hw_name })
const ECOBEE = [
  part('climate.my_ecobee', 'climate', 'hw-eco', 'My ecobee', 'My ecobee'),
  part('sensor.my_ecobee_humidity', 'sensor.humidity', 'hw-eco', 'My ecobee', 'My ecobee Humidity'),
  part('sensor.bedroom_temperature', 'sensor.temperature', 'hw-bed', 'Bedroom', 'Bedroom Temperature'),
  part('binary_sensor.bedroom_occupancy', 'motion', 'hw-bed', 'Bedroom', 'Bedroom Occupancy'),
]

async function pairAnEcobee(page: Page) {
  let paired = false
  const moves: string[] = []
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/move')) moves.push(`${new URL(r.url()).pathname} ${r.postData()}`) })
  await page.route('**/discovered*', route => route.fulfill({ json: [{ flow_id: 'f1', handler: 'homekit_controller', kind: 'HomeKit Device', title: 'My ecobee', source: 'zeroconf' }] }))
  await page.route('**/flows/f1', route => {
    const m = route.request().method()
    if (m === 'DELETE') return route.fulfill({ json: {} })
    if (m === 'GET') return route.fulfill({ json: { flow_id: 'f1', handler: 'homekit_controller', kind: 'HomeKit Device', type: 'form', step_id: 'pair',
      title: 'Pair with My ecobee', description: '', errors: {}, fields: [{ name: 'pairing_code', label: 'Pairing code', kind: 'string', required: true, default: '' }] } })
    paired = true
    return route.fulfill({ json: { flow_id: 'f1', handler: 'homekit_controller', kind: 'HomeKit Device', type: 'create_entry', entry_title: 'My ecobee' } })
  })
  await page.route('**/home*', async route => {
    const res = await route.fetch(), home = await res.json()
    if (paired) home.rooms.find((r: any) => r.id === 'unassigned').devices.push(...ECOBEE)
    await route.fulfill({ response: res, json: home })
  })
  await page.route('**/suggestions*', route => route.fulfill({ json: { assistant: false, items: [
    { id: 'sensor.bedroom_temperature', name: 'Bedroom temperature', room: 'bedroom', why: 'the room is in its name', source: 'house' },
    { id: 'climate.my_ecobee', name: 'Thermostat', room: 'living', why: 'a guess', source: 'assistant' },   // never placed without a tap
  ] } }))

  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await page.locator('.nudge', { hasText: 'My ecobee' }).first().click()
  await page.getByRole('button', { name: 'Set up' }).click()
  await page.locator('input').last().fill('123-45-678')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.locator('.arrived-row')).toHaveCount(2, { timeout: 20000 })
  return moves
}

test('it asks right there, a row a thing, with the sensor already in the room its name says', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const moves = await pairAnEcobee(page)

  await expect(page.locator('.flow-desc')).toHaveText('It brought a thermostat, and a temperature sensor.')
  await expect(page.locator('.arrived-from')).toContainText('Came with My ecobee')

  const bedroom = page.locator('.arrived-row', { hasText: 'Bedroom' }).filter({ hasText: 'its name says' })
  await expect(bedroom.locator('.chip-btn.on')).toHaveText('Bedroom')
  await expect(bedroom.getByRole('button', { name: 'Change' })).toBeVisible()
  await expect.poll(() => moves.filter(m => m.includes('/devices/sensor.bedroom_') || m.includes('/devices/binary_sensor.bedroom_')).length).toBe(1)
  expect(moves.some(m => m.includes('my_ecobee')), 'the assistant\'s guess is never placed without a tap').toBe(false)

  const thermostat = page.locator('.arrived-row', { hasText: 'My ecobee' })
  await expect(thermostat).toContainText('nothing says where this one is')
  await thermostat.getByRole('button', { name: 'Living room' }).click()
  await expect(thermostat.locator('.chip-btn.on')).toHaveText('Living room')        // it stays, chosen, under the finger
  await expect.poll(() => moves.filter(m => m.includes('climate.my_ecobee') && m.includes('living')).length).toBe(1)

  await expect(page.getByRole('button', { name: 'Put them in rooms' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Done' })).toBeVisible()
})

test('Change opens the rooms again on a row the house placed', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const moves = await pairAnEcobee(page)
  const bedroom = page.locator('.arrived-row').filter({ has: page.locator('.arrived-name b', { hasText: /^Bedroom$/ }) })
  await bedroom.getByRole('button', { name: 'Change' }).click()
  await bedroom.getByRole('button', { name: 'Office' }).click()
  await expect(bedroom.locator('.chip-btn.on')).toHaveText('Office')
  await expect.poll(() => moves.filter(m => m.includes('bedroom_') && m.includes('office')).length).toBe(1)
})
