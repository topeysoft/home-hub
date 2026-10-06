// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Share this house: what Apple Home, Google Home and Alexa are allowed to see. docs/matter.md.
 *
 * The screen is mostly one switch, and the tests are about what the switch is guarding rather than
 * about the switch. Three things have to be true on the glass, and each of them is a decision that
 * was made before the code:
 *
 *   - Nothing is shared until somebody says so, and the page says so in words rather than by being empty.
 *   - The code is behind a tap and is not sitting on a wall panel all day.
 *   - The lock switch is its own, is off, and says what it means -- Matter carries the unlock with the
 *     lock, so a household turning it on is agreeing to the half that opens the door.
 */
import { expect, test } from '@playwright/test'

const HUB = '/?sheet=share&at=19:40'
const section = (page: import('@playwright/test').Page) => page.locator('.page', { has: page.locator('.hub-rows') })

/* What is shared is the one thing in the mock house a test CHANGES, and the mock holds it for the
   whole process -- so these run in order and each one starts by putting it back. Without this they
   pass in whatever order the workers happen to pick and fail the first time somebody adds a sixth. */
test.describe.configure({ mode: 'serial' })
test.beforeEach(async ({ page }) => {
  await page.request.post('/share', { data: { on: false, kinds: ['light', 'switch', 'appliance'], locks: false, stopped: false } })
})

test('the page says what the feature IS before it says how it stands', async ({ page }) => {
  // The note this design answers: the screen never said the house's things BECOME Matter devices, to
  // be used by other Matter apps. The map is that sentence drawn, so it is drawn before anything is on.
  await page.goto(HUB, { waitUntil: 'networkidle' })
  const map = page.locator('.share-map')
  await expect(map).toBeVisible()
  await expect(map).toContainText('Matter')
  await expect(map).toContainText('Kitchen lights')          // this house's own things, not an abstraction
  for (const app of ['Apple Home', 'Google Home', 'Alexa']) await expect(map).toContainText(app)
  await expect(page.locator('.page-lede')).toContainText('Matter devices')
  // The door is the advertisement: nobody opens "Share this house" unless it says what it works with.
  await expect(page.locator('.door', { hasText: 'Share this house' })).toContainText('Apple Home, Google Home, Alexa')
})

test('the badge is ours, and nothing claims certification', async ({ page }) => {
  // The CSA's Matter mark may only go on a product they have certified, and this bridge is on a test
  // vendor id. Naming the standard is fine; wearing their badge is not. docs/matter.md, Certification.
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await expect(page.locator('.share-mark svg')).toBeVisible()
  await expect(page.locator('.page')).not.toContainText(/certified|certification/i)
})

test('a house that has not been asked says so, and offers one switch', async ({ page }) => {
  await page.goto(HUB, { waitUntil: 'networkidle' })
  const share = page.getByRole('switch', { name: 'Share this house' })
  await expect(share).toHaveAttribute('aria-checked', 'false')
  await expect(section(page)).toContainText('Off. Nothing about this house leaves it.')
  // Nothing else is drawn until it is on: no code, no kinds, and no lock switch to catch a finger.
  await expect(page.getByRole('switch', { name: 'Share locks and garage doors' })).toHaveCount(0)
  await expect(section(page)).not.toContainText('Scan this')
})

test('turning it on shows what is going out, and never the lock', async ({ page }) => {
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await page.getByRole('switch', { name: 'Share this house' }).click()

  await expect(section(page)).toContainText('None added yet.')
  for (const kind of ['Lights', 'Plugs and switches', 'Appliance features']) {
    await expect(page.getByRole('switch', { name: kind })).toHaveAttribute('aria-checked', 'true')
  }
  // The gated pair is a switch of its own, it starts off, and the sentence beside it is the decision.
  const locks = page.getByRole('switch', { name: 'Share locks and garage doors' })
  await expect(locks).toHaveAttribute('aria-checked', 'false')
  await expect(section(page)).toContainText('anything that can ask Siri, the Assistant or Alexa can unlock this door')
})

test('an alarm is never on offer, however the page is read', async ({ page }) => {
  // The refusal lives in the hub and is tested there; what is asserted here is that no screen ever
  // draws a way to ask for it. A switch nobody can reach is still worth not drawing.
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await page.getByRole('switch', { name: 'Share this house' }).click()
  await expect(section(page)).not.toContainText(/alarm|siren/i)
  await expect(page.getByRole('switch', { name: /alarm/i })).toHaveCount(0)
})

test('a kind switched off stops being described as going out', async ({ page }) => {
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await page.getByRole('switch', { name: 'Share this house' }).click()
  const plugs = page.getByRole('switch', { name: 'Plugs and switches' })
  await plugs.click()
  await expect(plugs).toHaveAttribute('aria-checked', 'false')
  await expect(section(page)).not.toContainText('Anything that is only on or off.')
  await expect(section(page)).toContainText('Every lamp and ceiling light')
})

/* A device's own page opens on a HOLD, not a tap -- a tap is the switch. The same dance as
   e2e/pane.spec.ts, kept short here because this file only ever opens the one lamp. */
async function openLamp(page: import('@playwright/test').Page) {
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  const tile = page.locator('.tile.light.dimmable').first()
  await expect(tile).toBeVisible()
  await page.waitForTimeout(500)
  const box = (await tile.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
  await page.mouse.down()
  await expect(page.locator('.opened-panel')).toHaveCount(1, { timeout: 10000 })
  await page.mouse.up()
  await page.waitForTimeout(600)
  return page.locator('.opened')
}

test('one lamp can be kept home, from its own page and not from a list', async ({ page }) => {
  // Apple Home cannot curate a bridge from its side, so if this hub does not offer it nobody can.
  // And it is on the device's own pane for the reason *Show this as* is: thirty-two rows of lamps is
  // the list the Share page exists to avoid drawing.
  await page.request.post('/share', { data: { on: true, left_out: [] } })
  const pane = await openLamp(page)
  const name = (await pane.locator('.opened-name').first().textContent())!.trim()
  await expect(pane.locator('.opened-share')).toContainText('Shared with other apps')
  await pane.getByRole('button', { name: 'Kept home' }).click()
  await expect(pane.locator('.opened-share')).toContainText('Kept out of other apps')
  await expect(pane.locator('.opened-share')).toContainText('this one stays in the house')

  // ...and the Share page counts it without ever naming it: the exception is a number there, and the
  // decision lives on the page of the thing it is about.
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await expect(section(page)).toContainText('kept home')
  await expect(section(page)).not.toContainText(name)
  await page.request.post('/share', { data: { left_out: [] } })
})

test('nothing offers to keep a thing home that was never going out', async ({ page }) => {
  await page.request.post('/share', { data: { on: true, kinds: ['switch'], left_out: [] } })
  const pane = await openLamp(page)
  await expect(pane.locator('.opened-share')).toHaveCount(0)
  await page.request.post('/share', { data: { kinds: ['light', 'switch', 'appliance'] } })
})

test('with no bridge running it says so, instead of offering a door with nothing behind it', async ({ page }) => {
  // The bug: Add an app answered "the door is open for five minutes" when there was no bridge, no
  // door, and nothing had happened -- on the one page about where a household's devices go.
  await page.request.post('/share', { data: { on: true, stopped: true } })
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await expect(section(page)).toContainText('has stopped')
  await expect(section(page)).toContainText('Your own lights and switches are unaffected.')
  await expect(page.getByRole('button', { name: 'Add an app' })).toHaveCount(0)
  await expect(section(page)).not.toContainText('Scan this')
  await page.request.post('/share', { data: { stopped: false } })
})

test('the code is behind a tap, and comes with the minutes it lasts', async ({ page }) => {
  // SHARED=held is a house an app already holds: the door is shut, so there is a button and no code.
  await page.goto(HUB, { waitUntil: 'networkidle' })
  await page.getByRole('switch', { name: 'Share this house' }).click()
  await expect(section(page)).toContainText('Scan this')     // nothing holds it yet, so it is waiting to be scanned
  await expect(section(page)).toContainText('0033-033-8072')
  await expect(section(page)).toContainText('five minutes')
  await expect(page.locator('.share-scan img')).toBeVisible()
})
