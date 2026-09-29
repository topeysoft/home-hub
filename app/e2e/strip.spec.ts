// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The strip-shaped part of a light's pane: one door, where it sits, and what is behind it.
 *
 * This is here because the arrangement drifted and nothing caught it. The two rows a strip added
 * went across the whole rig, under the brightness column as well, and the pane stopped fitting on a
 * wall -- every test passed, because every test asked what the panel DID rather than where it put
 * things. So this one measures: one row, starting where the colors start, below the three, and a
 * pane with nothing to scroll. design/strip/OneDoor.dc.html is the picture it is pinning.
 */
import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ timeout: 60_000 })
/* THE WALL IS 1440x900 (AGENTS.md section 1), and that is the screen this arrangement was drawn for
   and has to fit on. The suite's own wall is 1280x800, where the pane's 560px of words leave the rig
   too little for three columns and it folds -- gracefully, and still scrolling, which it did before
   this too. Measuring the fit there would be measuring a different screen. */
test.use({ viewport: { width: 1440, height: 900 } })

/** Hold the strip's tile until its pane opens. The press is the panel's own gesture; a tap toggles. */
async function openStrip(page: Page) {
  await page.goto('/?room=kitchen&at=19:40', { waitUntil: 'networkidle' })
  /* the tile, not the words on it: a press aimed above the name lands on whatever is above the tile,
     which here is a refrigerator and opens a perfectly good pane of the wrong kind */
  const tile = page.locator('.tile', { hasText: 'Under-cabinet strip' }).first()
  await expect(tile).toBeVisible()
  await page.waitForTimeout(500)
  const box = (await tile.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
  await page.mouse.down()
  await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10_000 })
  await page.mouse.up()
  await expect(page.locator('.rig-ask')).toBeVisible()
}

const box = (page: Page, sel: string) => page.locator(sel).first().boundingBox()

test('a strip adds one row, not two, and it is the only thing on the pane that says strip', async ({ page }) => {
  await openStrip(page)
  await expect(page.locator('.rig-ask .rig-card')).toHaveCount(1)
  await expect(page.getByText('Set up as a strip', { exact: false }).first()).toBeVisible()
  // the metres are on the row itself -- lights at sixty to the metre, said the way a strip is bought
  await expect(page.locator('.rig-ask')).toContainText(/About \d\.\d m/)
})

test('the row sits under the three and starts where the colors start', async ({ page }) => {
  await openStrip(page)
  const colors = (await box(page, '.rig-color'))!
  const levels = (await box(page, '.rig-levels'))!
  const ask = (await box(page, '.rig-ask'))!
  const bright = (await box(page, '.rig-col'))!
  // below the three, not beside them
  expect(ask.y).toBeGreaterThan(levels.y + levels.height - 1)
  // and not across the whole rig: it begins at the colors' left edge, clear of the brightness lane
  expect(Math.round(ask.x)).toBe(Math.round(colors.x))
  expect(ask.x).toBeGreaterThan(bright.x + bright.width)
  // which is what lets the brightness column run the full height again
  expect(bright.height).toBeGreaterThan(levels.height)
})

test('the whole pane is one screen, with nothing to scroll', async ({ page }) => {
  await openStrip(page)
  const rig = await page.locator('.pane-rig').evaluate(el => [el.scrollHeight, el.clientHeight])
  expect(rig[0]).toBeLessThanOrEqual(rig[1])
})

test('both questions are behind the one door, and the end can be walked', async ({ page }) => {
  await openStrip(page)
  await page.locator('.rig-ask .rig-card').click()
  const sheet = page.locator('.sd-sheet')
  await expect(sheet).toBeVisible()
  await expect(sheet).toContainText('Ends here')
  await expect(sheet).toContainText('The colors look wrong')

  /* A tap is one light. Six of them is a tenth of a metre, and both the picture and the metres say
     so while the finger is still there -- the strip is two rooms of wall away behind a television,
     and a control whose only answer is over there is one somebody presses twice. */
  const said = (await sheet.locator('.rig-card-name').first().innerText()).replace('Ends here ', '')
  const wide = sheet.locator('.sd-strip.wide i')
  const before = (await wide.boundingBox())!.width
  for (let i = 0; i < 6; i++) await sheet.getByText('Longer').click()
  await expect(sheet.locator('.rig-card-name').first()).not.toContainText(said)
  expect((await wide.boundingBox())!.width).toBeGreaterThan(before)

  await sheet.getByText('That’s it').click()
  await expect(sheet).toHaveCount(0)
  // and what it was walked to is what the row says afterwards, without being asked again
  await expect(page.locator('.rig-ask')).not.toContainText(said)

  // put the house back where it was found, so the next run of this measures what this one did
  await page.locator('.rig-ask .rig-card').click()
  for (let i = 0; i < 6; i++) await sheet.getByText('Shorter').click()
  await sheet.getByText('That’s it').click()
  await expect(page.locator('.rig-ask')).toContainText(said)
})

/* THE QUESTION OPENS ON TOP OF THE DOOR THAT ASKED IT. "The colors look wrong" hands the strip back
   to the setup conversation, which is a sheet of the whole panel -- and it drew underneath the pane
   holding the door, so the tap looked like it had done nothing. Asked of the browser rather than of
   the stylesheet: whatever is at the middle of the screen is what somebody would be looking at.
   The mock does not revisit, so the brain's answer is given here in the shape hub/strip.py returns. */
test('asking the colors again comes up over the door, not under it', async ({ page }) => {
  const asking = { state: 'order', asking: 'red', revisit: 'colors', name: 'Under-cabinet strip' }
  let revisited = false
  await page.route('**/strip/revisit', r => { revisited = true; return r.fulfill({ json: asking }) })
  await page.route(/\/strip$/, r => (revisited ? r.fulfill({ json: asking }) : r.fallback()))

  await openStrip(page)
  await page.locator('.rig-ask .rig-card').click()
  await expect(page.locator('.sd-sheet')).toBeVisible()
  await page.locator('.sd-sheet').getByText('The colors look wrong').click()

  await expect(page.getByText('Are the colors right?')).toHaveCount(1)
  const onTop = await page.evaluate(() => {
    const at = document.elementFromPoint(innerWidth / 2, innerHeight / 2)
    return { strip: !!at?.closest('.sheet:not(.sd-sheet)'), door: !!at?.closest('.sd-sheet'), pane: !!at?.closest('.opened') }
  })
  expect(onTop).toEqual({ strip: true, door: false, pane: false })
})
