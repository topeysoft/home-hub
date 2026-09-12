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
