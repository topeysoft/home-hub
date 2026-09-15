/* The weather, opened.
 *
 * The lozenge was scenery and is now the one piece of scenery that answers a finger, so most of
 * what is worth pinning here is about that boundary: that the tap actually lands (the row covers
 * the weather and swallowed it until panel.css raised the pane), that what opens has NO CONTROLS in
 * it, and that the house behind it is not disturbed.
 *
 * The empty row of verbs is the load-bearing assertion. WallView.vue's whole argument for letting
 * scenery be touched is that what opens is a reading — a pane with a power button in it would be
 * the lozenge quietly becoming a card.
 */
import { expect, test } from '@playwright/test'

const WALL = '/?layout=wall&nav=top&at=13:00'

async function home(page: import('@playwright/test').Page, url = WALL) {
  await page.goto(url, { waitUntil: 'networkidle' })
  await expect(page.locator('.bento').first()).toBeVisible()
  await page.waitForTimeout(1500)            // past the row's arrival
}

test('the lozenge opens, through the row that lies over it', async ({ page }) => {
  /* This is the regression. .bento is z-index 1 across the whole screen with 500-odd px of left
     padding holding the first card clear of the weather, so the row's empty half sits on top of the
     lozenge: before panel.css raised it, every tap here hit the scroller and nothing happened. */
  await home(page)
  const loz = page.locator('.wall-loz')
  const box = (await loz.boundingBox())!
  const on = await page.evaluate(([x, y]) => {
    const el = document.elementFromPoint(x, y)
    return el?.closest('.wall-loz') !== null
  }, [box.x + box.width / 2, box.y + box.height / 2])
  expect(on, 'something else is over the lozenge at its own centre').toBe(true)

  await loz.click()
  await expect(page.locator('.opened.outside')).toBeVisible()
  await expect(page.locator('.opened-name')).toHaveText(/cloudy|clear|rain|sun/i)
})

test('there is nothing to do to the weather', async ({ page }) => {
  /* The reason the tap is allowed at all. Every device pane has a row of verbs under the name; this
     one has none, and no other control either — so nothing about the house changes under it. */
  await home(page, `${WALL}&outside=1`)
  await expect(page.locator('.opened.outside')).toBeVisible()
  await expect(page.locator('.opened.outside .opened-acts')).toHaveCount(0)
  const controls = await page.locator('.opened.outside button').count()
  expect(controls, 'the weather pane has a control in it other than the way out').toBe(1)
  await expect(page.locator('.opened.outside .opened-close')).toBeVisible()
})

test('it says what is coming and what it is like in here', async ({ page }) => {
  await home(page, `${WALL}&outside=1`)
  // the forecast, at a size a 226px lozenge has no room for
  expect(await page.locator('.wx-hour').count()).toBeGreaterThan(4)
  expect(await page.locator('.wx-day').count()).toBeGreaterThan(2)
  await expect(page.locator('.wx-day').first()).toContainText('Today')
  // and the one number a weather app on a phone can never show
  await expect(page.locator('.opened.outside .opened-facts')).toContainText('Inside')
})

test('the hours are a shape, not eight of the same mark', async ({ page }) => {
  /* The bar is the reading's place between the coldest and warmest hour ON SHOW. An absolute scale
     would make a four-degree day a flat row of stubs, which is a chart that has stopped saying
     anything. */
  await home(page, `${WALL}&outside=1`)
  const bars = await page.locator('.wx-hour-bar').evaluateAll(els => els.map(e => Math.round(e.getBoundingClientRect().height)))
  expect(bars.length).toBeGreaterThan(4)
  expect(Math.max(...bars) - Math.min(...bars), 'every hour drew the same bar').toBeGreaterThan(20)
  expect(Math.min(...bars), 'an hour drew no bar at all').toBeGreaterThan(0)
})

test('the way out leaves the house exactly where it was', async ({ page }) => {
  /* Nothing vanishes under a tap: what was on the screen before the pane is still on it after. */
  await home(page)
  const before = await page.locator('.wall-loz').textContent()
  await page.locator('.wall-loz').click()
  await expect(page.locator('.opened.outside')).toBeVisible()
  await page.locator('.opened.outside .opened-close').click()
  await expect(page.locator('.opened.outside')).toHaveCount(0)
  await expect(page.locator('.wall-loz')).toBeVisible()
  expect(await page.locator('.wall-loz').textContent()).toBe(before)
  await expect(page.locator('.bento').first()).toBeVisible()
})

test('escape closes it too', async ({ page }) => {
  await home(page, `${WALL}&outside=1`)
  await expect(page.locator('.opened.outside')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.opened.outside')).toHaveCount(0)
})

test('a house with no forecast still gets a pane worth opening', async ({ page }) => {
  /* Plenty of weather integrations serve no forecast at all, and the hub hands through whatever it
     got (brain/hub/forecast.py). The pane must not open onto an empty box: what it knows without a
     forecast — the reading, the wind, the sun, the house's own temperature — is already more than
     the four lines on the lozenge. */
  await page.route('**/ambient', async route => {
    const res = await route.fetch()
    const body = await res.json()
    body.forecast = null
    await route.fulfill({ response: res, json: body })
  })
  await home(page, `${WALL}&outside=1`)
  await expect(page.locator('.opened.outside')).toBeVisible()
  await expect(page.locator('.wx-hour')).toHaveCount(0)
  await expect(page.locator('.opened.outside .opened-facts')).toContainText('Inside')
  await expect(page.locator('.opened-big')).toHaveText(/\d/)

  /* and the other half is not left empty. At a wall's width the instrument is most of the screen,
     so a pane that opened onto a blank box would be worse than the lozenge it came from: the sky's
     own drawing takes the space the rows would have had. */
  const art = page.locator('.wx-art')
  await expect(art).toBeVisible()
  const box = (await art.boundingBox())!
  expect(box.width, 'the drawing is not filling the space the forecast would have').toBeGreaterThan(200)
})

test('the receded lozenge does not eat the swipe it is invisible during', async ({ page }) => {
  /* It is raised over the row, so once it fades out on a scroll it has to stop taking touches as
     well — an invisible button lying over a scroller is worse than no button. */
  await home(page)
  await page.evaluate(() => {
    const row = document.querySelector('.bento') as HTMLElement
    row.style.scrollSnapType = 'none'
    row.scrollLeft = 400
  })
  await page.waitForTimeout(800)
  const pe = await page.locator('.wall-loz').evaluate(e => getComputedStyle(e).pointerEvents)
  expect(pe, 'the faded lozenge is still taking touches').toBe('none')
})
