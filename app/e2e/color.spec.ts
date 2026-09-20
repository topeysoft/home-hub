// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Asking a light to be a color, in the browser that is actually served the panel.

   color.test.ts pins the vocabulary -- what a light is on, what gets sent, which swatch wears the
   ring. None of that can see whether the control is on the screen, whether it is on the screen for
   a bulb that cannot do it, or whether a tap reaches the house. This can.

   The one it exists for most is the last test. Reading, Evening and Night carried a color
   temperature unconditionally, so tapping one on a lamp somebody had set to pink turned it white
   with nothing on the screen having said it would. That is invisible to every other kind of test:
   the preset worked, the service call succeeded, and the lamp was simply the wrong color. */
import { expect, test, type Page } from '@playwright/test'

/* the mock house: the living room's Ceiling light is a Hue pinned to a color and its Floor lamp can
   only dim; the office's Desk lamp is a Hue nobody has ever chosen a color for, which is Automatic.
   No device was added for these -- the wall boards were drawn at this house, and one card more or
   fewer moves the whole row. */
async function openLight(page: Page, name: string, room = 'living') {
  await page.goto(`/?room=${room}&at=20:10&wx=cloudy`, { waitUntil: 'networkidle' })
  const tile = page.locator('.tile.light', { has: page.locator(`text=${name}`) }).first()
  await expect(tile).toBeVisible()
  const box = (await tile.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + 40)
  await page.mouse.down()
  await page.waitForTimeout(900)                 // a hold, which is what opens a pane
  await page.mouse.up()
  await expect(page.locator('.rig-light')).toBeVisible()
}

/* what the panel actually asks the house for, which is the only proof a control is wired to
   anything. One entry per gesture: slide.ts only tells the house on the way up, because forty
   service calls to a Zigbee lamp is how a bulb falls off a mesh. */
function watchCalls(page: Page) {
  const sent: string[] = []
  page.route('**/devices/**', async (route) => {
    if (route.request().method() === 'POST') sent.push(route.request().postData() ?? '')
    await route.continue()
  })
  return sent
}

test('a light that can do color says so, and a tap reaches the house', async ({ page }) => {
  const sent = watchCalls(page)
  await openLight(page, 'Desk lamp', 'office')

  await expect(page.locator('.rig-color')).toBeVisible()
  /* by row rather than by total: this room may already have colors somebody kept, and a spec that
     counts every swatch on the screen is a spec that passes or fails on what the last one did */
  const rows = page.locator('.rig-color .rig-swatches')
  expect(await rows.nth(await rows.count() - 2).locator('.rig-swatch').count(), 'eight colors').toBe(8)
  expect(await rows.last().locator('.rig-swatch').count(), 'four whites').toBe(4)

  await page.locator('.rig-swatch').first().click()
  await expect.poll(() => sent.length).toBeGreaterThan(0)
  expect(sent[0], 'a swatch asks for a hue and an amount').toContain('hs_color')
})

/* The leak this replaced. The Warmth column asked for color_temp_kelvin, and a bulb in a color mode
   reports none -- so the control DISAPPEARED the moment a lamp went pink and there was no way back
   to white from this screen at all. White is a swatch beside the colors now, so it is reachable
   from wherever the lamp happens to be. */
test('white is reachable from a lamp that is currently a color', async ({ page }) => {
  const sent = watchCalls(page)
  await openLight(page, 'Ceiling light')          // pinned to a color in the mock

  const whites = page.locator('.rig-color .rig-swatches').last().locator('.rig-swatch')
  await expect(whites.first()).toBeVisible()
  await whites.nth(2).click()
  await expect.poll(() => sent.length).toBeGreaterThan(0)
  expect(sent[0], 'a white asks for a temperature').toContain('color_temp_kelvin')
})

/* And a light that cannot do either gets no block, rather than a row of controls that do nothing --
   the rule the Warmth column was already written to, now applied to the whole block. */
test('a lamp that can only dim is not offered a color', async ({ page }) => {
  await openLight(page, 'Floor lamp')
  await expect(page.locator('.rig-col').first()).toBeVisible()      // it still has a brightness
  await expect(page.locator('.rig-color')).toHaveCount(0)
})

/* THE ONE THIS FILE IS FOR. A preset is a brightness the house is used to; it used to carry a color
   temperature with it whatever the lamp was set to. */
test('a preset does not quietly whiten a lamp somebody set to a color', async ({ page }) => {
  const sent = watchCalls(page)
  await openLight(page, 'Ceiling light')          // pinned to a color

  await page.locator('.rig-card').first().click()                   // Reading
  await expect.poll(() => sent.length).toBeGreaterThan(0)
  expect(sent[0], 'the preset should change the brightness').toContain('brightness_pct')
  expect(sent[0], 'and must not undo the color').not.toContain('color_temp_kelvin')
})

/* while a lamp on Automatic has no color to protect, so the preset still carries the white -- for
   those the preset IS the whole answer */
test('but still carries the white for a lamp that has no color of its own', async ({ page }) => {
  const sent = watchCalls(page)
  await openLight(page, 'Desk lamp', 'office')           // on Automatic

  await page.locator('.rig-card').first().click()
  await expect.poll(() => sent.length).toBeGreaterThan(0)
  expect(sent[0]).toContain('brightness_pct')
  expect(sent[0]).toContain('color_temp_kelvin')
})

/* THE THIRTEENTH COLOR, and keeping it. A color matched by eye against this room's own lamps is
   worth more than any preset -- a bulb's idea of pink is not a swatch's -- so making somebody find
   it twice is the failure. The kept one has to come back in the grid, which is the only part of
   this a unit test cannot see: it travels panel -> hub -> settings -> /home -> panel. */
test('a color tuned against the room can be kept, and comes back in the grid', async ({ page }) => {
  await openLight(page, 'Desk lamp', 'office')

  await page.locator('.rig-more').click()
  await expect(page.locator('.rig-hue')).toBeVisible()

  // put the hue somewhere that is not one of the eight, which is the whole point of being here
  const hue = (await page.locator('.rig-hue').boundingBox())!
  await page.mouse.move(hue.x + hue.width / 2, hue.y + hue.height * 0.38)
  await page.mouse.down()
  await page.mouse.up()
  await page.waitForTimeout(300)

  /* it may already be kept from an earlier run against the same mock, which is itself the right
     answer -- near enough is the same color -- so the assertion is that the card ENDS up saying so */
  const card = page.locator('.rig-keep-card')
  if (await card.isEnabled()) await card.click()
  await expect(card, 'the card should say it is kept').toHaveClass(/\bon\b/)

  await page.locator('.rig-back').click()
  await expect(page.locator('.rig-color')).toBeVisible()
  await expect(page.locator('.rig-color .rig-lbl').first(), 'the kept color joins the grid').toHaveText('This room')
})

/* The pane is assembled from a shell and a rig, and --lamp -- the accent for the power button, the
   brightness column, the lit preset -- lives on the shell. So a magenta lamp opened into an amber
   screen with the swatch it was set to ringed two feet away. Nothing that reads one component can
   see that; it only shows when the whole pane is on screen at once. */
test('the pane is lit in the color the lamp actually is', async ({ page }) => {
  await openLight(page, 'Ceiling light')          // pinned to a color in the mock

  const lit = await page.evaluate(() => {
    const px = (s: string) => getComputedStyle(document.querySelector(s)!).backgroundColor
    return { chip: px('.opened-acts .ctl.primary'), lamp: getComputedStyle(document.querySelector('.opened-panel')!).getPropertyValue('--lamp').trim() }
  })
  const [r, g, b] = lit.chip.match(/\d+/g)!.slice(0, 3).map(Number)
  /* not amber. --lamp is rgb(233,184,114); a power button anywhere near it here means the shell
     never heard about the bulb, which is exactly the bug. */
  expect(Math.hypot(r - 233, g - 184, b - 114), `power button is ${lit.chip}`).toBeGreaterThan(60)
  expect(lit.lamp, 'and the accent itself is the bulb').toContain('226')
})

/* while a warm white lamp keeps the amber, which is not a fallback -- it is what it is emitting */
test('and a warm white lamp keeps lamplight', async ({ page }) => {
  await openLight(page, 'Floor lamp')
  const chip = await page.evaluate(() => getComputedStyle(document.querySelector('.opened-acts .ctl.primary')!).backgroundColor)
  const [r, g, b] = chip.match(/\d+/g)!.slice(0, 3).map(Number)
  expect(Math.hypot(r - 233, g - 184, b - 114), `power button is ${chip}`).toBeLessThan(30)
})
