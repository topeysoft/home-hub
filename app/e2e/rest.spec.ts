// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The panel resting with something left open in front of it.
 *
 * The resting screen is the sky, the clock, and three lines about the house — and it is drawn ABOVE
 * everything else on the shell. Every part of the house recedes for it: the rail, the stage, the
 * bars. A device pane did not, so a lamp opened at bedtime sat there fully lit with the time
 * floating over it and no sky behind it at all, which reads as a rendering fault rather than as a
 * house at rest.
 *
 * The clock is Playwright's rather than a three-minute wait, and jumped rather than run: the panel
 * keeps several intervals, and running four minutes of them tick by tick takes longer than the wait
 * it replaces.
 *
 * A SHEET THAT OPENED ITSELF is the other half, and it was missed. Every other sheet is somewhere a
 * person navigated to, which keeps the panel awake; a bridge knocking arrives on its own, so it can
 * still be up when the three minutes run out. It made the same fault twice over -- the clock landed
 * on live text, and the sheet's own veil blacked out the sky the resting screen is mostly made of.
 */
import { expect, test, type Page } from '@playwright/test'

const REST_AFTER = '04:00'

async function holdOpen(page: Page) {
  const tile = page.locator('.tile.light.dimmable').first()
  await expect(tile).toBeVisible()
  await page.waitForTimeout(600)
  const box = (await tile.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
  await page.mouse.down()
  await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10000 })
  await page.mouse.up()
  await page.waitForTimeout(700)
}

test('the house at rest takes an opened device with it', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  await holdOpen(page)

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()
  await page.waitForTimeout(1200)             // the fade is 0.9s

  const pane = page.locator('.opened')
  await expect(pane).toHaveCSS('opacity', '0')
  /* and it takes no touches while it cannot be seen: the first press on a resting screen is the one
     that wakes it, and it must not also land on the veil of a pane nobody can see */
  await expect(pane).toHaveCSS('pointer-events', 'none')
  await expect(page.locator('.idle-time')).toBeVisible()
})

test('waking brings the house back, not what was left open', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  await holdOpen(page)

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()
  await page.waitForTimeout(1000)

  await page.mouse.click(720, 450)
  await page.waitForTimeout(1000)
  await expect(page.locator('.idle')).toHaveCount(0)
  await expect(page.locator('.opened-panel'), 'the pane came back with the house').toHaveCount(0)
  await expect(page.locator('.shell')).not.toHaveClass(/opened-shell/)
  await expect(page.locator('.stage')).toHaveCSS('opacity', '1')
})

/* A bridge knocks by itself, so unlike every other sheet it can be on screen when the house rests. */
async function knocking(page: Page) {
  await page.route('**/bridge', r => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ bridges: 1, waiting: 0, state: 'knocking', how: 'air' }),
  }))
}

test('the house at rest takes a sheet that opened itself with it', async ({ page }) => {
  await knocking(page)
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.sheet-back')).toBeVisible()

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()
  await page.waitForTimeout(1200)             // the fade is 0.9s

  const sheet = page.locator('.sheet-back')
  await expect(sheet, 'the clock had been landing on top of live text').toHaveCSS('opacity', '0')
  await expect(sheet, 'and the first press must wake the wall, not answer the bridge').toHaveCSS('pointer-events', 'none')
  /* the whole point of the resting screen: the sky is behind it again, not the sheet's own veil */
  await expect(page.locator('.idle-time')).toBeVisible()
  await expect(page.locator('.idle-weather')).toBeVisible()
})

test('waking brings the knock back, because the bridge is still knocking', async ({ page }) => {
  await knocking(page)
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.sheet-back')).toBeVisible()

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()
  await page.waitForTimeout(1000)

  await page.mouse.click(720, 820)
  await page.waitForTimeout(1200)
  await expect(page.locator('.idle')).toHaveCount(0)
  /* NOT like a device pane, which the house leaves behind: that was only ever this screen's, and a
     knock is the house's. It is still true when the screen comes back, so it is still on it. */
  await expect(page.locator('.sheet-back')).toHaveCSS('opacity', '1')
  await expect(page.getByRole('button', { name: 'That\u2019s the one' })).toBeVisible()
})

test('a bridge knocking wakes the wall, the way a phone at the door does', async ({ page }) => {
  /* The screen has gone dark and somebody plugs a bridge in beside it. They are standing right
     there, so the wall comes back on -- the same event, and the same answer, as a phone knocking. */
  let knocks = false
  await page.route('**/bridge', r => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify(knocks ? { bridges: 1, waiting: 0, state: 'knocking', how: 'air' }
                                 : { bridges: 1, waiting: 0, state: 'none' }),
  }))
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle')).toBeVisible()

  knocks = true
  /* store.ts asks /bridge once a minute while there is no job running, and every two seconds once
     there is. So the knock lands on the next slow poll. */
  await page.clock.fastForward('01:10')
  await expect(page.locator('.idle'), 'the wall came back on for it').toHaveCount(0)
  await expect(page.locator('.sheet-back')).toHaveCSS('opacity', '1')
  await expect(page.getByText('A bridge is here.')).toBeVisible()
})

test('a knock nobody answers does not hold the wall awake', async ({ page }) => {
  /* It says `knocking` every two seconds until somebody deals with it. Waking on the state rather
     than on its arrival would mean a wall that can never rest again, which is worse than the fault
     this fixed. */
  await knocking(page)
  await page.clock.install({ time: new Date('2026-09-13T19:40:00') })
  await page.goto('/?at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.sheet-back')).toBeVisible()

  await page.clock.fastForward(REST_AFTER)
  await expect(page.locator('.idle'), 'it rested with the knock still standing').toBeVisible()
  await page.clock.fastForward('01:00')                       // and thirty more polls do not undo it
  await expect(page.locator('.idle')).toBeVisible()
})
