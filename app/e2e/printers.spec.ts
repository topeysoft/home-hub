// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* 3D printers on the wall and the phone, pinned to the boards the household chose on 2 October 2026
 * (design/printers/, B with an optional room). These measure where things are, not only that they are
 * there: a print leads Your afternoon with no buttons on it; the band does not repeat a card; the pane has
 * the printer's own two actions and Stop asks twice; a room is chosen from the pane with No room at the
 * top; a printer with a room is a tile there and its room ranks up while it prints; and Add says where to
 * tap, then the answer, in the row that asked. Each one fails on purpose if the arrangement drifts.
 *
 * The mock has printers only for a page that asks for them (?printers=, mock/printers.mjs), so every
 * other test still sees the house the other boards were drawn at.
 */
import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ timeout: 60_000 })
test.use({ viewport: { width: 1440, height: 900 } })

const box = async (page: Page, sel: string) => (await page.locator(sel).first().boundingBox())!
/* each test its own copy of the mock's printer house: the mock keys it by the page's address */
let n = 0
const at = (q: string) => `/?at=14:47&printers=${q}&k=${process.pid}-${++n}`

test.describe('a print leads Your afternoon (NowB, StatesB)', () => {
  test('the print is the first card in the row, a whole row tall, with no buttons while it prints', async ({ page }) => {
    await page.goto(at('1'), { waitUntil: 'networkidle' })
    const cards = page.locator('.bento > .bento-card')
    await expect(cards.first()).toHaveClass(/print-card/)
    await expect(cards.first()).toContainText('Phone stand')
    await expect(cards.first()).toContainText('42%')
    await expect(cards.first()).toContainText('Layer 118 of 280')
    await expect(cards.first()).toContainText('Done at')
    await expect(cards.first().locator('button')).toHaveCount(0)
    // as tall as the row's tallest card, and the TV card is the next one along
    const card = await box(page, '.print-card'), tv = await box(page, '.bento .tile.media')
    expect(card.height).toBeGreaterThan(tv.height)
    expect(card.x).toBeLessThan(tv.x)
    // the ready printer and the one stopped with nothing on its bed are not cards
    await expect(page.locator('.print-card')).toHaveCount(1)
  })

  test('a stopped printer with nothing printing is the band’s line, and its row opens its pane', async ({ page }) => {
    await page.goto(at('1'), { waitUntil: 'networkidle' })
    const line = page.locator('.nudge', { hasText: 'Something needs a look' })
    await expect(line).toContainText('R2D2 stopped')
    await line.click()
    await page.getByRole('button', { name: 'Open R2D2' }).click()
    await expect(page.locator('.print-pane .opened-name')).toHaveText('R2D2')
    await expect(page.locator('.print-pane')).toContainText('The toolhead isn’t answering.')
  })

  test('waiting for you: the printer’s own two answers are on the card, and the band does not say it again', async ({ page }) => {
    await page.goto(at('needs_you'), { waitUntil: 'networkidle' })
    const card = page.locator('.print-card.waiting')
    await expect(card).toContainText('OBI1 needs you')
    await expect(card.locator('.print-answer')).toHaveText(['Switch to slot 6', 'Resume'])
    await expect(page.locator('.nudge', { hasText: 'needs a look' })).toHaveCount(0)
  })

  test('done: the card is drained and says when it finished', async ({ page }) => {
    await page.goto(at('finished'), { waitUntil: 'networkidle' })
    const card = page.locator('.print-card.done')
    await expect(card).toContainText('OBI1: Phone stand is done')
    await expect(card.locator('.print-finished')).toContainText('Finished')
    await expect(card.locator('button')).toHaveCount(0)
  })
})

test.describe('the printer’s pane (Pane, RoomChoiceB)', () => {
  test('words on the left, the camera on the right, the temperatures in °C, and the hub’s limit said once', async ({ page }) => {
    await page.goto(at('1'), { waitUntil: 'networkidle' })
    await page.locator('.print-card').click()
    const pane = page.locator('.print-pane')
    await expect(pane.locator('.print-room')).toHaveText(/No room · Choose/)
    await expect(pane.locator('.print-doing')).toHaveText('Printing Phone stand')
    await expect(pane.locator('.print-temp')).toHaveText(['Nozzle220°C', 'Bed60°C', 'Chamber38°C'])
    await expect(pane).toContainText('Starting a print, and saying the bed is clear, happen at OBI1.')
    await expect(pane.locator('.print-act')).toHaveText(['Pause', 'Stop print'])
    const words = await box(page, '.print-pane .pane-said'), cam = await box(page, '.print-pane-cam')
    expect(cam.x).toBeGreaterThan(words.x + words.width)
    expect(cam.width).toBeGreaterThan(600)
  })

  test('Stop asks twice, and nothing is asked of the printer on the first tap', async ({ page }) => {
    const asked: string[] = []
    page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/action')) asked.push(r.postData() ?? '') })
    await page.goto(at('1'), { waitUntil: 'networkidle' })
    await page.locator('.print-card').click()
    await page.locator('.print-act.cancel').click()
    await expect(page.locator('.print-ask')).toContainText('Stop Phone stand?')
    expect(asked).toEqual([])
    await page.getByRole('button', { name: 'Keep printing' }).click()
    await expect(page.locator('.print-act')).toHaveText(['Pause', 'Stop print'])
    await page.locator('.print-act.pause').click()
    await expect(page.locator('.print-doing')).toHaveText('Paused.')       // the printer's own answer, at once
    expect(asked).toEqual([JSON.stringify({ action: 'pause', args: {} })])
  })

  test('Choose opens the pane’s own room picker, with No room at the top, and the room is kept', async ({ page }) => {
    await page.goto(at('1'), { waitUntil: 'networkidle' })
    await page.locator('.print-card').click()
    await page.getByRole('button', { name: 'Choose' }).click()
    const pick = page.locator('.print-pane select')
    await expect(pick.locator('option').first()).toHaveText('No room')
    await expect(pick.locator('option').last()).toHaveText('A new room…')
    await pick.selectOption('office')
    await page.getByRole('button', { name: 'Done' }).click()
    await expect(page.locator('.print-room')).toHaveText('Office')
  })
})

test.describe('with a room chosen (WorkshopB, RankedB)', () => {
  test('the printer is a tile in its room and a chip on its line, printing first', async ({ page }) => {
    await page.goto(at('room') + '&room=office', { waitUntil: 'networkidle' })
    await expect(page.locator('.room-head .lede')).toHaveText(/^OBI1 printing · C3PO ready/)
    await expect(page.locator('.printer-chip')).toHaveText(['OBI1printing, 42%', 'C3POready'])
    const tall = page.locator('.printer-tile.tall')
    await expect(tall).toHaveAttribute('data-size', 'full')
    await expect(page.locator('.printer-tile.ready')).toHaveAttribute('data-size', 'third')
    expect((await box(page, '.tiles > *')).x).toBe((await box(page, '.printer-tile.tall')).x)
  })

  test('printing counts as on: the room ranks right behind the one with the television on', async ({ page }) => {
    await page.goto(at('room'), { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Rooms' }).click()
    const second = page.locator('.rooms-bento > .room-cell').nth(1)
    await expect(second).toContainText('Office')
    await expect(second).toContainText('OBI1 printing, 42%')
    await expect(second).toContainText('Printing')
    await expect(second).toHaveAttribute('data-size', 'half')
    /* and the printing card takes an ordinary slot: once the arrival has settled the bento ends flush,
       four columns on their own tracks and nothing past the stage's right edge, exactly as shipped */
    await expect.poll(() => page.locator('.rooms-bento').evaluate(g => g.scrollWidth - g.clientWidth)).toBe(0)
    await expect.poll(async () => {
      const xs = await page.locator('.rooms-bento > .room-cell').evaluateAll(cs => cs.map(c => Math.round(c.getBoundingClientRect().x)))
      return [...new Set(xs)].length
    }).toBe(4)
    const right = await page.locator('.rooms-bento').evaluate(g => g.getBoundingClientRect().right)
    for (const r of await page.locator('.rooms-bento > .room-cell').evaluateAll(cs => cs.map(c => c.getBoundingClientRect().right)))
      expect(r).toBeLessThanOrEqual(right + 0.5)
  })

  test('and Your afternoon is unchanged: the print still leads it', async ({ page }) => {
    await page.goto(at('room'), { waitUntil: 'networkidle' })
    await expect(page.locator('.bento > .bento-card').first()).toHaveClass(/print-card/)
  })
})

test.describe('letting a printer in (FoundLine, AddList, AddAsking, AddAnswers)', () => {
  test('found printers are the band’s line and a dot on the + door, never a screen', async ({ page }) => {
    await page.goto(at('found'), { waitUntil: 'networkidle' })
    const line = page.locator('.nudge', { hasText: 'Found 3 new things nearby' })
    await expect(line).toContainText('OBI1, R2D2 and C3PO, 3D printers')
    await expect(page.locator('.topbar-add').first()).toHaveClass(/attention/)
    await expect(page.locator('.house')).toHaveCount(0)
  })

  test('Add lists printers on this Wi-Fi apart from the rest, one row and one button each', async ({ page }) => {
    await page.goto(at('found') + '&sheet=add', { waitUntil: 'networkidle' })
    const block = page.locator('.add-block', { hasText: 'Printers on this Wi‑Fi' })
    await expect(block.locator('.printer-title')).toHaveText(['OBI1', 'R2D2', 'C3PO'])
    await expect(block.locator('.printer-sub').first()).toHaveText('3D printer')
    await expect(page.locator('.add-block .label').last()).toHaveText('Or choose what you’re adding')
  })

  test('the row that asked says where to tap, counts down, and then says it was let in, in the same place', async ({ page }) => {
    await page.goto(at('found') + '&sheet=add', { waitUntil: 'networkidle' })
    const first = page.locator('.printer-row').first()
    const before = await first.boundingBox()
    await first.getByRole('button', { name: 'Add' }).click()
    await expect(first.locator('.printer-asking-title')).toHaveText('Tap Allow on OBI1’s screen')
    await expect(first.locator('.printer-asking-left')).toContainText('left')
    await expect(first.getByRole('button', { name: 'Stop asking' })).toBeVisible()
    // the mock's somebody at the printer taps Allow a few seconds later
    await expect(first.locator('.printer-title')).toHaveText('OBI1 is in the house', { timeout: 15_000 })
    await expect(first).toContainText('Printing Phone stand, 42%. It’s on Your afternoon now.')
    expect((await first.boundingBox())!.y).toBe(before!.y)
  })

  test('each way an ask ends is said in the row that asked, with what to do next', async ({ page }) => {
    await page.goto(at('answers') + '&sheet=add', { waitUntil: 'networkidle' })
    const rows = page.locator('.printer-row .printer-title')
    await expect(rows).toHaveText(['OBI1 is in the house', 'R2D2 said no', 'Nobody answered on C3PO'])
    await expect(page.locator('.printer-row.refused').getByRole('button', { name: 'Ask again' })).toBeVisible()
    await expect(page.locator('.printer-row.allowed').getByRole('button', { name: 'Open' })).toBeVisible()
  })

  test('This house gains Printers, where a printer with no print and no room lives', async ({ page }) => {
    await page.goto(at('1') + '&sheet=house', { waitUntil: 'networkidle' })
    const door = page.locator('.door', { hasText: 'Printers' })
    await expect(door).toContainText('R2D2 stopped')
    await door.click()
    await expect(page.locator('.printer-row .printer-title')).toHaveText(['C3PO', 'OBI1', 'R2D2'])
    const c3po = page.locator('.printer-row', { hasText: 'C3PO' })
    await c3po.getByRole('button', { name: 'Forget' }).click()
    await expect(c3po).toContainText('Forget C3PO? The hub comes off its list of devices too.')
  })
})

test.describe('on a phone (PhoneB, PhonePaneB)', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the print is a short block of its own under the band, and opens as a sheet with the camera across its top', async ({ page }) => {
    await page.goto(at('1') + '&layout=stack', { waitUntil: 'networkidle' })
    const block = page.locator('.block', { hasText: 'Printing' })
    await expect(block.locator('.print-card.compact')).toContainText('42%')
    await block.locator('.print-card').click()
    const cam = await box(page, '.print-pane-cam'), name = await box(page, '.print-pane .opened-name')
    expect(cam.y).toBeLessThan(name.y)
    expect(cam.width).toBeGreaterThan(380)
    await expect(page.locator('.print-limit-narrow')).toHaveText('Starting a print happens at OBI1.')
  })
})
