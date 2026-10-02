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

/* THE ROOFLINE'S OWN PANE, DRAWN (design/roofline/DrawnC.dc.html, chosen 1 October 2026). The roof as
 * the house knows it across the floor of the pane -- the runs in the order they go round, each as long as
 * its lights, an arrow for the way each leaves its box, the boxes by place under it -- with brightness a
 * bar along the top of the right side and the look and its evenings side by side beneath it. A dark run
 * is dark where it is, ringed, with its one next step under it. None of a lamp's colors or levels. */
async function openRoof(page: Page, kind: string) {
  await page.goto(`/?room=backyard&at=18:52&roofline=${kind}`, { waitUntil: 'networkidle' })
  await hold(page, '.tile.light:has-text("Roofline")')
  await expect(page.locator('.roof-plate')).toHaveCount(1)
  await page.waitForTimeout(900)    // the pane rises into place; measure where it lands
}
const boxesOf = async (page: Page, sel: string) => {
  const out = []
  for (const l of await page.locator(sel).all()) out.push((await l.boundingBox())!)
  return out
}
/* Nothing on the pane scrolls: no element inside it is taller than the box it is drawn in. */
const scrollers = (page: Page) => page.evaluate(() => [...document.querySelectorAll('.opened *')]
  .filter(e => e.scrollHeight > e.clientHeight + 1 && ['auto', 'scroll'].includes(getComputedStyle(e).overflowY))
  .map(e => `${e.className} ${e.scrollHeight}/${e.clientHeight}`))

/* A house sharing its lights with other apps, answered here rather than switched on in the mock, which
   other tests share: the share state is held in the page, and a light kept home is kept here too. */
async function shareLights(page: Page) {
  let left: string[] = []
  let last: Record<string, unknown> = {}
  const shape = () => ({ ...last, on: true, ready: true, kinds: [...new Set([...((last.kinds as string[]) ?? []), 'light'])], left_out: left })
  await page.route('**/share', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    const r = await route.fetch()
    last = await r.json()
    await route.fulfill({ response: r, json: shape() })
  })
  await page.route(/\/devices\/[^/]+\/share$/, async route => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/')[2])
    const wanted = !!route.request().postDataJSON()?.shared
    left = wanted ? left.filter(x => x !== id) : [...new Set([...left, id])]
    await route.fulfill({ json: shape() })
  })
}

test.describe('the Roofline’s own pane: the roof, drawn (pane: C)', () => {
  test('the roof is drawn across the floor of the pane, under the bar and the two cards', async ({ page }) => {
    await openRoof(page, 'christmas')
    const plate = await box(page, '.roof-plate'), bar = await box(page, '.roof-bar')
    const look = await box(page, '.roof-look'), eve = await box(page, '.roof-evenings')
    const name = await box(page, '.opened-name'), why = await box(page, '.pane-why')
    // the plate is the floor: below the bar and both cards, below the left column's sentence, and as wide as the pane
    expect(plate.y).toBeGreaterThan(bar.y + bar.height)
    expect(plate.y).toBeGreaterThan(look.y + look.height - 1)
    expect(plate.y).toBeGreaterThan(eve.y + eve.height - 1)
    expect(plate.y).toBeGreaterThan(why.y + why.height - 1)
    expect(Math.abs(plate.x - name.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(plate.x + plate.width - (bar.x + bar.width))).toBeLessThanOrEqual(2)
    // and it starts where the board starts it, 610 down a 900 wall, with what it says inside the wall
    expect(Math.abs(plate.y - 610)).toBeLessThanOrEqual(12)
    const last = await boxesOf(page, '.roof-plate .roof-box-label, .roof-plate .roof-said')
    for (const b of last) expect(b.y + b.height).toBeLessThanOrEqual(900)
  })

  test('the runs in the order they go round, each as long as its lights, with an arrow for the way it leaves its box', async ({ page }) => {
    await openRoof(page, 'christmas')
    const runs = page.locator('.roof-plate .roof-run')
    await expect(runs).toHaveCount(4)
    const ids = await runs.evaluateAll(els => els.map(e => `${(e as HTMLElement).dataset.chip}${(e as HTMLElement).dataset.run}`))
    expect(ids).toEqual(['a1', 'b1', 'b2', 'c1'])
    const b = await boxesOf(page, '.roof-plate .roof-run')
    for (let i = 1; i < b.length; i++) expect(b[i].x).toBeGreaterThan(b[i - 1].x + b[i - 1].width - 1)
    // 110, 110, 96, 96 lights: the same width per light, within a few percent
    const per = [110, 110, 96, 96].map((n, i) => b[i].width / n)
    for (const p of per) expect(Math.abs(p / per[0] - 1)).toBeLessThan(0.04)
    expect(b[0].width).toBeGreaterThan(b[2].width)
    // two turned round: their arrows point back toward the start
    const dirs = await page.locator('.roof-plate .roof-arrow').evaluateAll(els => els.map(e => (e as HTMLElement).dataset.dir))
    expect(dirs).toEqual(['on', 'back', 'on', 'back'])
    // the boxes by place underneath, in the order they are along the roof, each one Fine
    await expect(page.locator('.roof-plate .roof-box-place')).toHaveText(['Left corner', 'Right of the door', 'Garage end'])
    await expect(page.locator('.roof-plate .roof-box-state')).toHaveText(['Fine', 'Fine', 'Fine'])
    const bx = await boxesOf(page, '.roof-plate .roof-box')
    expect(bx[0].x).toBeLessThan(b[0].x)
    expect(bx[1].x).toBeGreaterThan(b[1].x + b[1].width - 1)
    expect(bx[1].x + bx[1].width).toBeLessThan(b[2].x + 1)
    expect(bx[2].x).toBeGreaterThan(b[3].x + b[3].width - 1)
    await expect(page.locator('.roof-plate .roof-ring')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Which way round' })).toBeVisible()
  })

  test('brightness is a bar along the top, and the look and its evenings sit side by side under it', async ({ page }) => {
    await openRoof(page, 'christmas')
    const bar = await box(page, '.roof-bar'), look = await box(page, '.roof-look'), eve = await box(page, '.roof-evenings')
    await expect(page.locator('.roof-bar')).toHaveAttribute('role', 'slider')
    expect(bar.width).toBeGreaterThan(bar.height * 5)
    expect(look.y).toBeGreaterThan(bar.y + bar.height - 1)
    expect(Math.round(look.y)).toBe(Math.round(eve.y))
    expect(eve.x).toBeGreaterThan(look.x + look.width - 1)
    expect(Math.abs(look.x - bar.x)).toBeLessThanOrEqual(2)
    expect(Math.abs(eve.x + eve.width - (bar.x + bar.width))).toBeLessThanOrEqual(2)
    const lookCard = page.locator('.roof-look')
    await expect(lookCard).toContainText('Christmas')
    await expect(lookCard).toContainText('Dec 1 – Jan 6')
    await expect(lookCard).toContainText('Red and green, chasing each other slowly')
    await expect(lookCard.getByRole('button', { name: 'Moving' })).toHaveAttribute('aria-pressed', 'true')
    await expect(lookCard.getByRole('button', { name: 'Hold it still' })).toHaveAttribute('aria-pressed', 'false')
    await expect(lookCard.getByRole('button', { name: 'Say another look' })).toBeVisible()
    const eveCard = page.locator('.roof-evenings')
    await expect(eveCard).toContainText('On at dusk, off at 11:00')
    await expect(eveCard.getByRole('button', { name: 'Every evening' })).toHaveAttribute('aria-pressed', 'true')
    await expect(eveCard.getByRole('button', { name: 'Only in an occasion' })).toBeVisible()
    await expect(eveCard.getByRole('button', { name: 'Not by itself' })).toBeVisible()
  })

  test('none of a lamp’s colors, Automatic or levels, and nothing scrolls on the wall', async ({ page }) => {
    await openRoof(page, 'christmas')
    const pane = page.locator('.opened')
    await expect(pane.locator('.rig-swatch')).toHaveCount(0)
    await expect(pane.locator('.rig-auto')).toHaveCount(0)
    await expect(pane.locator('.rig-levels')).toHaveCount(0)
    await expect(pane).not.toContainText('Reading')
    await expect(pane).not.toContainText('More colors')
    expect(await scrollers(page)).toEqual([])
    // the left column keeps what every light has: room, name, the round buttons and the percentage, with one sentence
    const bar = await box(page, '.roof-bar')
    for (const s of ['.opened-room', '.opened-name', '.opened-acts', '.opened-big', '.pane-why']) {
      const b = await box(page, s)
      expect(b.x + b.width).toBeLessThan(bar.x)
    }
    await expect(page.locator('.opened-acts .ctl')).toHaveCount(3)
    await expect(page.locator('.pane-why')).toHaveText('On at dusk because it keeps evenings.')
  })

  test('a dark run is dark where it is, ringed, with its one next step under it, and the sentence says so', async ({ page }) => {
    await openRoof(page, 'dark')
    const ring = await box(page, '.roof-plate .roof-ring')
    const runs = await boxesOf(page, '.roof-plate .roof-run')
    await expect(page.locator('.roof-plate .roof-run.dark')).toHaveCount(1)
    await expect(page.locator('.roof-plate .roof-run').nth(3)).toHaveClass(/dark/)
    // the ring holds the garage end's run and nothing of the run before it
    expect(ring.x).toBeLessThanOrEqual(runs[3].x)
    expect(ring.x + ring.width).toBeGreaterThanOrEqual(runs[3].x + runs[3].width)
    expect(ring.x).toBeGreaterThan(runs[2].x + runs[2].width - 1)
    const next = page.locator('.roof-plate .roof-said')
    await expect(next).toHaveText('On a different power supply. Plug the 12 V supply back in.')
    await expect(next).toHaveClass(/wrong/)
    const n = (await next.boundingBox())!
    expect(n.y).toBeGreaterThan(ring.y + ring.height)
    expect(n.y + n.height).toBeLessThanOrEqual(900)
    await expect(page.locator('.roof-plate .roof-box-state')).toHaveText(['Fine', 'Fine', 'Dark'])
    await expect(page.locator('.pane-why')).toHaveText('On, but the garage end is dark.')
    expect(await scrollers(page)).toEqual([])
  })

  /* SHARING IS SAID BY THE ROOM (design/roofline/SaidB.dc.html, chosen 2 October 2026). In a house that
     shares its lights with other apps the share row would make the left column taller than the board's,
     so on this pane it folds to a chip on the room's line, and the pane is DrawnC to the pixel: the roof
     is the same box, full width along the floor, shared or not. The chip opens the same choice as a small
     card over the name, and the card stays where the finger left it until the pane is touched elsewhere. */
  test('in a house sharing its lights with other apps, the roof keeps the width of the wall and sharing is a chip on the room’s line', async ({ page }) => {
    await openRoof(page, 'dark')
    const unshared = await box(page, '.roof-plate'), plainName = await box(page, '.opened-name')
    await expect(page.locator('.room-share')).toHaveCount(0)

    await shareLights(page)
    await openRoof(page, 'dark')
    // no share row in the left column: the left column is the board's
    await expect(page.locator('.pane-said .opened-kind')).toHaveCount(0)
    // the roof is the same box it is in a house that does not share
    const plate = await box(page, '.roof-plate'), bar = await box(page, '.roof-bar'), name = await box(page, '.opened-name')
    for (const k of ['x', 'y', 'width', 'height'] as const) expect(Math.abs(plate[k] - unshared[k])).toBeLessThanOrEqual(2)
    expect(Math.abs(name.y - plainName.y)).toBeLessThanOrEqual(1)
    expect(Math.abs(plate.x + plate.width - (bar.x + bar.width))).toBeLessThanOrEqual(2)
    await expect(page.locator('.roof-plate .roof-ring')).toHaveCount(1)

    // the chip, on the room's line beside the room's name, with the light's own color as its dot
    const chip = page.locator('.opened-room .room-share')
    await expect(chip).toHaveText('Shared with other apps')
    await expect(chip.locator('.room-share-dot')).toHaveCount(1)
    await expect(chip).toHaveAttribute('aria-expanded', 'false')
    const room = await box(page, '.opened-room'), c = await box(page, '.opened-room .room-share')
    expect(Math.abs((c.y + c.height / 2) - (room.y + room.height / 2))).toBeLessThanOrEqual(2)
    expect(c.y + c.height).toBeLessThan(name.y + 6)
    expect(c.x + c.width).toBeLessThan(bar.x)
    await expect(page.locator('.room-share-card')).toHaveCount(0)

    // a tap opens the same choice over the name: Shared and Kept home, and what it means
    await chip.click()
    const card = page.locator('.room-share-card')
    await expect(card).toBeVisible()
    await expect(chip).toHaveAttribute('aria-expanded', 'true')
    await expect(card.getByRole('button', { name: 'Shared' })).toHaveAttribute('aria-pressed', 'true')
    await expect(card.getByRole('button', { name: 'Kept home' })).toHaveAttribute('aria-pressed', 'false')
    await expect(card).toContainText('Apple Home, Google Home and Alexa can see this one')
    const k = await box(page, '.room-share-card')
    expect(k.y).toBeGreaterThan(room.y + room.height - 1)
    expect(k.y).toBeLessThan(name.y + name.height)
    expect(k.x + k.width).toBeLessThan(bar.x)
    expect(await page.evaluate(() => {
      const r = document.querySelector('.room-share-card')!.getBoundingClientRect()
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height - 12)
      return !!hit?.closest('.room-share-card')
    })).toBe(true)

    // choosing keeps the card where it is, and the chip says what the light now is: its own undo
    await card.getByRole('button', { name: 'Kept home' }).click()
    await expect(card.getByRole('button', { name: 'Kept home' })).toHaveAttribute('aria-pressed', 'true')
    await expect(card).toBeVisible()
    await expect(card).toContainText('this one stays in the house')
    await expect(chip).toHaveText('Kept out of other apps')
    await expect(chip.locator('.room-share-dot')).toHaveCount(0)
    const still = await box(page, '.room-share-card')
    expect(Math.abs(still.x - k.x)).toBeLessThanOrEqual(1)
    expect(Math.abs(still.y - k.y)).toBeLessThanOrEqual(1)
    const after = await box(page, '.roof-plate')
    for (const key of ['x', 'y', 'width', 'height'] as const) expect(Math.abs(after[key] - unshared[key])).toBeLessThanOrEqual(2)
    await card.getByRole('button', { name: 'Shared' }).click()
    await expect(chip).toHaveText('Shared with other apps')
    await expect(card).toBeVisible()

    // it closes when the pane is touched anywhere else, or by the chip, and the chip stays
    await page.locator('.opened-big').click()
    await expect(card).toHaveCount(0)
    await expect(chip).toBeVisible()
    await chip.click()
    await expect(card).toBeVisible()
    await chip.click()
    await expect(card).toHaveCount(0)
    await expect(page.locator('.opened')).toHaveCount(1)

    const n = await box(page, '.roof-plate .roof-said')
    expect(n.y + n.height).toBeLessThanOrEqual(900)
    expect(await scrollers(page)).toEqual([])
  })

  /* NOT DECIDED (pane-shared-decided): while the pane is being edited, Take it out of the house is a quiet
     row in the left column, and the build's present answer stands for that case alone -- the roof keeps
     to the right-hand column. Pinned so a change to it is a choice, not an accident. */
  test('while it is being edited, the roof still keeps to the right of the quiet rows', async ({ page }) => {
    await openRoof(page, 'christmas')
    await page.getByRole('button', { name: 'Rename or move it' }).click()
    await expect(page.locator('.pane-said .opened-end')).toBeVisible()
    const plate = await box(page, '.roof-plate'), look = await box(page, '.roof-look'), said = await box(page, '.pane-said')
    expect(plate.x).toBeGreaterThanOrEqual(look.x - 1)
    expect(plate.x).toBeGreaterThan(said.x + said.width - 1)
    expect(plate.y).toBeGreaterThan(look.y + look.height - 1)
    expect(await scrollers(page)).toEqual([])
  })

  test('held still, Hold it still is the one chip lit and the look says so', async ({ page }) => {
    await openRoof(page, 'still')
    const lookCard = page.locator('.roof-look')
    await expect(lookCard.getByRole('button', { name: 'Hold it still' })).toHaveAttribute('aria-pressed', 'true')
    await expect(lookCard.getByRole('button', { name: 'Moving' })).toHaveAttribute('aria-pressed', 'false')
    await expect(lookCard).toContainText('Red and green, held still')
  })

  test('before the way round is known, each box’s runs are drawn apart, and the pill is the ask', async ({ page }) => {
    await openRoof(page, 'ask')
    await expect(page.locator('.roof-plate')).toHaveAttribute('data-order', 'unknown')
    await expect(page.locator('.roof-plate .roof-run')).toHaveCount(4)
    await expect(page.locator('.roof-plate .roof-group')).toHaveCount(3)
    const g = await boxesOf(page, '.roof-plate .roof-group')
    for (let i = 1; i < g.length; i++) expect(g[i].x - (g[i - 1].x + g[i - 1].width)).toBeGreaterThan(40)
    await expect(page.locator('.roof-plate .roof-said')).toHaveText('Christmas goes round the house. Show it which way round?')
  })

  test('Which way round opens the yard, and Say another look opens the command box', async ({ page }) => {
    const asked: string[] = []
    page.on('request', r => { if (r.method() === 'POST') asked.push(new URL(r.url()).pathname) })
    await openRoof(page, 'christmas')
    await page.getByRole('button', { name: 'Which way round' }).click()
    await expect.poll(() => asked).toContain('/roofline/yard')
    await openRoof(page, 'christmas')
    await page.locator('.roof-look').getByRole('button', { name: 'Say another look' }).click()
    await expect(page.locator('.opened')).toHaveCount(0)
    const input = page.locator('.say-box input').first()
    await expect(input).toBeFocused()
    await expect(input).toHaveValue('Christmas: ')
  })
})

test.describe('the Roofline’s pane on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  test('the same pane folded: the bar, the two cards one above the other, and the roof across the phone', async ({ page }) => {
    await page.goto('/?room=backyard&at=18:52&roofline=dark', { waitUntil: 'networkidle' })
    await hold(page, '.tile.light:has-text("Roofline")')
    await expect(page.locator('.roof-plate')).toHaveCount(1)
    await page.waitForTimeout(900)
    const bar = await box(page, '.roof-bar'), look = await box(page, '.roof-look'), eve = await box(page, '.roof-evenings')
    const plate = await box(page, '.roof-plate')
    expect(bar.width).toBeGreaterThan(bar.height * 3)
    expect(eve.y).toBeGreaterThan(look.y + look.height - 1)
    expect(plate.y).toBeGreaterThan(eve.y + eve.height - 1)
    for (const b of [bar, look, eve, plate]) { expect(b.x).toBeGreaterThanOrEqual(0); expect(b.x + b.width).toBeLessThanOrEqual(390) }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    const runs = await boxesOf(page, '.roof-plate .roof-run')
    expect(runs).toHaveLength(4)
    for (let i = 1; i < runs.length; i++) expect(runs[i].x).toBeGreaterThan(runs[i - 1].x + runs[i - 1].width - 1)
    // the places do not print over each other
    const places = await boxesOf(page, '.roof-plate .roof-box-label')
    for (let i = 1; i < places.length; i++) expect(places[i].x).toBeGreaterThanOrEqual(places[i - 1].x + places[i - 1].width - 1)
    await expect(page.locator('.roof-plate .roof-ring')).toHaveCount(1)
  })

  test('in a house that shares, the chip is on the room’s line and its card fits the phone', async ({ page }) => {
    await shareLights(page)
    await page.goto('/?room=backyard&at=18:52&roofline=dark', { waitUntil: 'networkidle' })
    await hold(page, '.tile.light:has-text("Roofline")')
    await expect(page.locator('.roof-plate')).toHaveCount(1)
    await page.waitForTimeout(900)
    await expect(page.locator('.pane-said .opened-kind')).toHaveCount(0)
    const chip = page.locator('.opened-room .room-share')
    await expect(chip).toHaveText('Shared with other apps')
    const room = await box(page, '.opened-room'), c = await box(page, '.opened-room .room-share'), name = await box(page, '.opened-name')
    expect(Math.abs((c.y + c.height / 2) - (room.y + room.height / 2))).toBeLessThanOrEqual(2)
    expect(c.x + c.width).toBeLessThanOrEqual(390)
    await chip.click()
    const card = page.locator('.room-share-card')
    await expect(card).toBeVisible()
    const k = await box(page, '.room-share-card')
    expect(k.x).toBeGreaterThanOrEqual(0)
    expect(k.x + k.width).toBeLessThanOrEqual(390)
    expect(k.y).toBeLessThan(name.y + name.height)
    await card.getByRole('button', { name: 'Kept home' }).click()
    await expect(chip).toHaveText('Kept out of other apps')
    await expect(card).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    // and the roof is still across the phone, under the cards
    const eve = await box(page, '.roof-evenings'), plate = await box(page, '.roof-plate')
    expect(plate.y).toBeGreaterThan(eve.y + eve.height - 1)
    expect(plate.x + plate.width).toBeLessThanOrEqual(390)
  })
})

/* Every other light keeps the pane it had: the column, Automatic, the colors and the three levels, in the
   places they were measured at on 1 October before the Roofline's pane was built (1440x900). */
test('a lamp’s pane is unchanged beside the roofline', async ({ page }) => {
  await page.goto('/?room=living&at=18:52&roofline=christmas', { waitUntil: 'networkidle' })
  await hold(page, '.tile.light:has-text("Ceiling light")')
  await page.waitForTimeout(1200)
  await expect(page.locator('.roof-plate')).toHaveCount(0)
  await expect(page.locator('.roof-bar')).toHaveCount(0)
  await expect(page.locator('.rig-auto')).toContainText('Automatic')
  await expect(page.locator('.rig-levels .rig-card')).toHaveCount(3)
  const at = async (s: string) => { const b = await box(page, s); return [b.x, b.y, b.width, b.height].map(Math.round) }
  const near = (got: number[], want: number[]) => got.forEach((v, i) => expect(Math.abs(v - want[i])).toBeLessThanOrEqual(1))
  near(await at('.pane-rig'), [643, 298, 748, 489])
  near(await at('.rig-col'), [670, 325, 168, 401])
  near(await at('.rig-color'), [864, 382, 292, 321])
  near(await at('.rig-levels'), [1182, 382, 182, 321])
  near(await at('.pane-facts'), [49, 682, 560, 67])
  near(await at('.pane-day'), [49, 809, 1342, 61])
})

test.describe('the roofline (moves: A with C, evenings: B, one: C then A)', () => {
  test('one tile saying the occasion', async ({ page }) => {
    await page.goto('/?room=backyard&at=18:52&roofline=ask', { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.light', { hasText: 'Roofline' })).toContainText('On · Christmas')
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
