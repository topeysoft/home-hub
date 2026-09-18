// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A phone at the door.

   The panel has always ranked this above everything else it can tell a person -- App.vue wakes the
   wall for it, and nothing else -- and then drew it as a card in a strip underneath "An update is
   ready". These hold the three things that changed: it is a pane of its own, it looks the same at
   every hour, and it costs the arrangement nothing.

   The house is stubbed rather than started with knobs, because a locked house with a knock in it is
   a different house from the one the rest of the suite drives, and a spec that needs its own mock
   is a spec nobody runs. Only two endpoints move: the status gains `locked`, without which the
   store throws the asks away, and /phones answers with somebody at the door. */
import { expect, test, type Page } from '@playwright/test'

const ASK = { id: 'a1', name: "Sam's iPhone", kind: 'phone', asked: Math.round(Date.now() / 1000) - 30 }

async function knocking(page: Page, asks: unknown[] = [ASK]) {
  await page.route('**/setup/status', async (route) => {
    const res = await route.fetch()
    route.fulfill({ json: { ...(await res.json()), locked: true } })
  })
  await page.route('**/phones', (route) => route.fulfill({ json: { phones: [], asks } }))
}

test('a knock opens a pane of its own, not a card in the strip', async ({ page }) => {
  await knocking(page)
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.ask-pane')).toHaveCount(1)
  await expect(page.locator('.ask-pane .opened-name')).toContainText("Sam's iPhone")
  // and nothing is left sitting in the band while the pane is up
  await expect(page.locator('.nudge.ask')).toHaveCount(0)
  // the room recedes behind it the way it does behind any pane
  expect(await page.getAttribute('.shell', 'class')).toContain('opened-shell')
})

/* The reason this pane is fixed where every other surface tracks the sky: it is the one place a
   person hands out a key to the house, and recognising it instantly -- noticing when something
   about it is off -- is the only defence they have against answering a prompt they should not.
   A surface that looks different at every hour cannot be recognised, so this is the one test in
   the suite that WANTS two hours to come out identical. */
test('it looks the same at every hour, which is the point of it', async ({ page }) => {
  const paint = async (at: string) => {
    await page.goto(`/?face=glass&layout=wall&nav=top&at=${at}`, { waitUntil: 'networkidle' })
    await expect(page.locator('.ask-pane')).toHaveCount(1)
    await page.waitForTimeout(900)
    return page.locator('.ask-pane .opened-panel').evaluate((el) => {
      const cs = getComputedStyle(el)
      return [cs.backgroundImage, cs.backgroundColor, cs.color].join(' | ')
    })
  }
  await knocking(page)
  const night = await paint('21:30')
  const noon = await paint('12:30&wx=sunny')
  expect(noon, 'the pane a person is meant to recognise changed with the hour').toBe(night)
})

test('putting it aside leaves the knock standing, and the chip brings it back', async ({ page }) => {
  await knocking(page)
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await page.locator('.ask-pane .opened-close').click()
  await expect(page.locator('.ask-pane')).toHaveCount(0)

  // the strand is not lost: the band carries it, and it is the one chip there wearing a lit edge
  const chip = page.locator('.nudge.ask')
  await expect(chip).toHaveCount(1)
  await expect(chip).toContainText("Sam's iPhone")
  await chip.click()
  await expect(page.locator('.ask-pane')).toHaveCount(1)
})

/* The whole reason a pane and not a card: a pane is over the arrangement rather than in it, so the
   row Wall was drawn around keeps the height it was drawn with while somebody is at the door.

   Asserted as the mechanism rather than as two measurements of the row, and that is deliberate. A
   before-and-after needs a house with nothing at the door to measure first, `locked` is what
   decides whether the house is asked about phones at ALL, and it also decides whether the band is
   carrying "Lock the settings" -- so the baseline moves for a reason that has nothing to do with
   the knock, and the live stream can push a status in underneath it either way. Out of flow is the
   whole claim, and it is a fact about one element. */
test('a phone at the door is over the arrangement, not in it', async ({ page }) => {
  await knocking(page)
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.ask-pane')).toHaveCount(1)
  await page.waitForTimeout(900)

  const how = await page.locator('.ask-pane').evaluate((el) => {
    const cs = getComputedStyle(el)
    return { position: cs.position, inRow: !!el.closest('.home'), covers: el.getBoundingClientRect().height }
  })
  expect(how.position, 'a pane that is in the flow pushes whatever is under it').toBe('fixed')
  expect(how.inRow, 'the pane is inside the arrangement it is supposed to be over').toBe(false)
  expect(how.covers).toBe(800)
})

/* Nobody is at the door once the house is not showing.

   The narrow path the relay creates, and it is a transition rather than a steady state: a phone sitting at home
   with an ask already in hand, whose owner then walks out. `store.asks` is already full, the next request comes back
   through the relay, the house declines to open, and the pane would rise over the screen saying so. It cannot happen
   by the asks LOADING from away -- everything is 403ing by then -- which is why it is worth a test rather than an
   argument: the state is reachable only through a door that has already shut behind it. */
test('a knock does not rise over a house that is not showing', async ({ page }) => {
  await knocking(page)
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40&away=1', { waitUntil: 'networkidle' })
  await expect(page.locator('.away')).toHaveCount(1)
  await page.waitForTimeout(1200)
  await expect(page.locator('.ask-pane'), 'a phone at the door rose over the away screen').toHaveCount(0)
  // and the shell is not pretending something is open on top of it either
  expect(await page.getAttribute('.shell', 'class')).not.toContain('opened-shell')
})

/* The pane is the question. Once it has been answered it is not a question any more, and leaving it
   standing on a wall -- the same phone, the same two buttons -- invites the next person past to answer
   it again. It used to stand there because it only left when the hub said the ask was gone, and the hub
   did not say so until the phone itself came back for the key. The fall starts on the tap instead. */
test('answering it puts it away, and says so on the way out', async ({ page }) => {
  await knocking(page)
  await page.route('**/phones/asks/a1/allow', (route) => route.fulfill({ json: { id: 'p1', name: "Sam's iPhone" } }))
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  const pane = page.locator('.ask-pane')
  await pane.getByRole('button', { name: 'Let it in' }).click()
  await pane.getByRole('button', { name: 'Keep' }).click()
  await expect(page.locator('.ask-pane'), 'the pane stood there after the phone was let in').toHaveCount(0)
  // and the knock is answered, not put aside: nothing is left in the band offering to open it again
  await expect(page.locator('.nudge.ask')).toHaveCount(0)
  // the word the pane was carrying survives it
  await expect(page.getByText("Sam's iPhone is in.")).toBeVisible()
})

test('saying not now puts it away too', async ({ page }) => {
  await knocking(page)
  await page.route('**/phones/asks/a1', (route) => route.fulfill({ json: { ok: true } }))
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await page.locator('.ask-pane').getByRole('button', { name: 'Not now' }).click()
  await expect(page.locator('.ask-pane')).toHaveCount(0)
  await expect(page.locator('.nudge.ask')).toHaveCount(0)
})

/* One at a time means the next one arrives the way the first did -- rising -- rather than the pane
   staying open and swapping the name under a finger that is still coming down on a button. */
test('the phone behind it rises on its own', async ({ page }) => {
  const second = { id: 'a2', name: "Ada's phone", kind: 'phone', asked: Math.round(Date.now() / 1000) - 10 }
  await knocking(page, [ASK, second])
  await page.route('**/phones/asks/a1/allow', (route) => route.fulfill({ json: { id: 'p1', name: "Sam's iPhone" } }))
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  const pane = page.locator('.ask-pane')
  await expect(pane.locator('.ask-more')).toContainText('One more phone is waiting')
  await pane.getByRole('button', { name: 'Let it in' }).click()
  await pane.getByRole('button', { name: 'Keep' }).click()
  await expect(pane.locator('.opened-name')).toContainText("Ada's phone")
  await expect(pane.locator('.ask-more')).toHaveCount(0)
  // it came back up, rather than never having gone down
  await page.waitForTimeout(600)
  expect(await page.getAttribute('.ask-pane', 'class')).toContain('shown')
  // and it is back at the first question, not still holding the spans the last answer was picked from
  await expect(pane.getByRole('button', { name: 'Let it in' })).toBeVisible()
})

test('letting one in asks for how long, and says so', async ({ page }) => {
  await knocking(page)
  await page.goto('/?face=glass&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  // scoped to the pane: "Back" also lives inside "Open Backyard cam camera" out on the row
  const pane = page.locator('.ask-pane')
  await pane.getByRole('button', { name: 'Let it in' }).click()
  for (const span of ['For today', 'For the weekend', 'Keep'])
    await expect(pane.getByRole('button', { name: span })).toBeVisible()
  // and there is a way back out of the question that is not an answer to it
  await pane.getByRole('button', { name: 'Back' }).click()
  await expect(pane.getByRole('button', { name: 'Let it in' })).toBeVisible()
})
