// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A strip controller and a roofline on the wall, pinned to the boards the household chose on 1 October
 * (design/controller-panel/ and design/roofline/). These measure where things are, not only that they
 * are there: a held strip says Staying off on its tile and first on the room's line, its pane says why in
 * the left column with the instrument left at half strength, Needs a look carries its row first; the
 * second strip is one question with two pictures side by side; the roofline's sheet is one screen; and
 * the yard flow fits a phone. Each one fails on purpose if the arrangement drifts from its board.
 *
 * Every screen here is held still with the preview params (?held=, ?strip=, ?roofline=), because a real
 * controller holds a strip dark for a reason nobody stages (AGENTS.md §4).
 */
import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ timeout: 60_000 })
test.use({ viewport: { width: 1440, height: 900 } })

const box = async (page: Page, sel: string) => (await page.locator(sel).first().boundingBox())!

async function hold(page: Page, sel: string) {
  const t = page.locator(sel).first()
  await expect(t).toBeVisible()
  await page.waitForTimeout(400)
  const b = (await t.boundingBox())!
  await page.mouse.move(b.x + b.width / 2, b.y + Math.min(24, b.height / 2))
  await page.mouse.down()
  await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10_000 })
  await page.mouse.up()
}

test.describe('a strip held dark (held: A with B’s row)', () => {
  test('its tile says Staying off and why, and the room’s line says it first', async ({ page }) => {
    await page.goto('/?room=kitchen&at=19:42&held=supply', { waitUntil: 'networkidle' })
    const tile = page.locator('.tile.light.held')
    await expect(tile).toHaveCount(1)
    await expect(tile).toContainText('Under-cabinet strip')
    await expect(tile.locator('.held-state')).toHaveText('Staying off')
    await expect(tile.locator('.held-why')).toHaveText('It’s on a different power supply')
    // no dimmer and no drawing: the tile stops claiming a state it cannot have
    await expect(tile.locator('.fill')).toHaveCount(0)
    const first = page.locator('.room-line > *').first()
    await expect(first).toHaveClass(/held-line/)
    await expect(first).toContainText('The strip is staying off to protect itself')
    await expect(first).toContainText('Why?')
  })

  test('a tap opens why, and asks nothing of the strip', async ({ page }) => {
    const asked: string[] = []
    page.on('request', r => { if (r.method() === 'POST' && /\/act|\/devices\/k2/.test(r.url())) asked.push(r.url()) })
    await page.goto('/?room=kitchen&at=19:42&held=supply', { waitUntil: 'networkidle' })
    await page.locator('.tile.light.held').click()
    await expect(page.locator('.opened-big')).toHaveText('Staying off')
    expect(asked).toEqual([])
  })

  test('its pane says why in the left column, the supplies and one step, and dims the instrument', async ({ page }) => {
    await page.goto('/?room=kitchen&at=19:42&held=supply', { waitUntil: 'networkidle' })
    await page.locator('.tile.light.held').click()
    await expect(page.locator('.held-step')).toContainText('Plug the 12 V supply back in')
    await page.waitForTimeout(900)    // the pane rises into place; measure where it lands, not where it is on the way
    const big = await box(page, '.opened-big'), text = await box(page, '.held-text')
    const supplies = await box(page, '.held-supplies'), step = await box(page, '.held-step'), rig = await box(page, '.pane-rig')
    // one column, in reading order, under the big state, left of the instrument
    expect(text.y).toBeGreaterThan(big.y + big.height - 1)
    expect(supplies.y).toBeGreaterThan(text.y + text.height - 1)
    expect(step.y).toBeGreaterThan(supplies.y + supplies.height - 1)
    for (const b of [big, text, supplies, step]) expect(b.x + b.width).toBeLessThan(rig.x)
    // and all of it on one screen
    expect(step.y + step.height).toBeLessThanOrEqual(900)
    await expect(page.locator('.held-supply').first()).toContainText('12 V')
    await expect(page.locator('.held-supply.now')).toContainText('24 V')
    // the power button stays, disabled rather than gone; the instrument is there at half strength
    await expect(page.locator('.opened-acts .ctl.primary')).toBeDisabled()
    const op = await page.locator('.pane-rig.held > *').first().evaluate(el => getComputedStyle(el).opacity)
    expect(Number(op)).toBeCloseTo(0.5, 2)
  })

  test('running hot changes nothing on the tile', async ({ page }) => {
    await page.goto('/?room=kitchen&at=19:42&held=hot', { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.light.held')).toHaveCount(0)
    await expect(page.locator('.held-line')).toHaveCount(0)
  })

  test('Needs a look carries its row first, with Show me, and the band says it in a few words', async ({ page }) => {
    await page.goto('/?at=19:42&held=supply', { waitUntil: 'networkidle' })
    await expect(page.locator('.nudge', { hasText: 'The kitchen strip is staying off' })).toBeVisible()
    await page.goto('/?at=19:42&held=supply&sheet=notes', { waitUntil: 'networkidle' })
    const row = page.locator('.notes li').first()
    await expect(row).toHaveClass(/note-held/)
    await expect(row).toContainText('Under-cabinet strip is staying off.')
    await expect(page.locator('.page-lede')).toContainText('the parts of it that need you')
    await row.getByRole('button', { name: 'Show me' }).click()
    await expect(page.locator('.opened-big')).toHaveText('Staying off')
  })
})

test.describe('the second strip (runs: C) and one wire or two (wire: C then A)', () => {
  test('one question, with the two strips as the picture, side by side, Part of this light first', async ({ page }) => {
    await page.goto('/?at=19:42&strip=second', { waitUntil: 'networkidle' })
    await expect(page.locator('.sheet.strip h2')).toHaveText('There’s a second strip.')
    const picks = page.locator('.two-picks .pick')
    await expect(picks).toHaveCount(2)
    await expect(picks.nth(0)).toContainText('Part of this light')
    await expect(picks.nth(1)).toContainText('A light of its own')
    const a = (await picks.nth(0).boundingBox())!, b = (await picks.nth(1).boundingBox())!
    expect(Math.round(a.y)).toBe(Math.round(b.y))
    expect(b.x).toBeGreaterThan(a.x + a.width - 1)
    // both lit is one light; one lit and one dark is two
    await expect(picks.nth(0).locator('i.lit')).toHaveCount(2)
    await expect(picks.nth(1).locator('i.lit')).toHaveCount(1)
  })

  test('its colors are asked again, "too"', async ({ page }) => {
    await page.goto('/?at=19:42&strip=second-red', { waitUntil: 'networkidle' })
    await expect(page.locator('.sheet.strip h2')).toHaveText('Is it red too?')
  })

  test('an unclear reading asks once more: lit, or still dark', async ({ page }) => {
    await page.goto('/?at=19:42&strip=lit', { waitUntil: 'networkidle' })
    await expect(page.locator('.sheet.strip h2')).toHaveText('Is it lit now?')
    await expect(page.getByRole('button', { name: 'Yes, it’s lit' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Still dark' })).toBeVisible()
  })
})

test.describe('the roofline (moves: A with C, evenings: B, one: C then A)', () => {
  test('one tile saying the occasion; behind its row, one screen of boxes, its way round, its evenings and Hold it still', async ({ page }) => {
    await page.goto('/?room=backyard&at=18:52&roofline=ask', { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.light', { hasText: 'Roofline' })).toContainText('On · Christmas')
    await hold(page, '.tile.light')
    await expect(page.locator('.rig-ask')).toContainText('Three boxes, four runs')
    await page.locator('.rig-ask .rig-card').click()
    const sheet = page.locator('.roof-sheet')
    await expect(sheet).toBeVisible()
    const s = (await sheet.boundingBox())!
    expect(s.y).toBeGreaterThanOrEqual(0)
    expect(s.y + s.height).toBeLessThanOrEqual(900)
    await expect(sheet.locator('.roof-boxes li')).toHaveCount(3)
    await expect(sheet).toContainText('Christmas goes round the house. Show it which way round?')
    await expect(sheet.getByRole('button', { name: 'Every evening' })).toHaveAttribute('aria-pressed', 'true')
    await expect(sheet.getByRole('button', { name: 'Hold it still' })).toBeVisible()
    // two columns on the wall: what it is on the left, when and how it looks on the right
    const cols = sheet.locator('.roof-cols > div')
    const l = (await cols.nth(0).boundingBox())!, r = (await cols.nth(1).boundingBox())!
    expect(r.x).toBeGreaterThan(l.x + l.width - 1)
  })

  test('a dark part says which and why, and the roof is still on', async ({ page }) => {
    await page.goto('/?room=backyard&at=18:52&roofline=dark', { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.light', { hasText: 'Roofline' })).toContainText('the garage end is dark')
  })

  test('a look is said, and plays as a draft with its words as chips', async ({ page }) => {
    await page.goto('/?at=18:52', { waitUntil: 'networkidle' })
    await page.locator('.say-box input').first().fill('Christmas: red and green, chasing')
    await page.keyboard.press('Enter')
    const card = page.locator('.say-look')
    await expect(card).toContainText('For Christmas, on the roofline')
    await expect(card.locator('.say-look-word.on')).toHaveText('chasing')
    await expect(card).toContainText('Playing on the roof now')
    await expect(card.getByRole('button', { name: 'Keep it for Christmas' })).toBeVisible()
    await expect(card.getByRole('button', { name: 'Not this' })).toBeVisible()
  })
})

test.describe('which way round, on a phone in the yard (TapA)', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  test('colors in the order tapped, the turned one said, and the one button at the foot', async ({ page }) => {
    await page.goto('/?at=18:12&roofline=yard', { waitUntil: 'networkidle' })
    const rows = page.locator('.yard-row')
    await expect(rows).toHaveCount(4)
    await expect(rows.locator('.yard-name')).toHaveText(['Red', 'Blue', 'Green', 'Pink'])
    await expect(rows.nth(1)).toContainText('Turned round')
    await expect(rows.nth(0).locator('.yard-end')).toHaveText('1st')
    const go = (await box(page, '.yard-go')), last = (await rows.nth(3).boundingBox())!
    expect(go.y).toBeGreaterThan(last.y + last.height)
    expect(go.y + go.height).toBeLessThanOrEqual(844)
    const sheet = (await box(page, '.yard-sheet'))
    expect(Math.round(sheet.width)).toBe(390)
  })
})
