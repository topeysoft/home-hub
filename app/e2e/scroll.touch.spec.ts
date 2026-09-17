/* A row that scrolls sideways has to scroll under a finger that lands on a card, because on the
   panel there is nowhere else for a finger to land: the cards ARE the row. A mouse pass cannot
   catch this -- `touch-action` only speaks to touch -- and the first real touch screen this ran on
   (an Echo Show in a kitchen) scrolled the rooms list and nothing else. Dispatched through CDP, the
   path a real finger takes, so the browser's own pan logic is what is being tested. */
import { expect, test, type Page } from '@playwright/test'

/* The wall panel's size, not the touch project's iPad: under 861px every one of these rows folds
   into a column and there is nothing sideways to scroll. */
test.use({ viewport: { width: 1280, height: 800 }, hasTouch: true })

/* A finger swiping leftwards across whatever sits at (x, y): down, a run of moves, up. */
async function swipe(page: Page, x: number, y: number, dx: number) {
  const cdp = await page.context().newCDPSession(page)
  try {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    const steps = 12
    for (let i = 1; i <= steps; i++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x - (dx * i) / steps, y }] })
      await page.waitForTimeout(16)
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  } finally {
    await cdp.detach()
  }
}

type Row = { what: string; url: string; tab?: string; scroller: string; card: string }

/* ?nav=top pins the tabbed panel whatever the mock's look says; the Rooms tab has no URL knob of
   its own, so it is reached the way a person reaches it. */
async function swipesUnderAFinger(page: Page, { what, url, tab, scroller, card }: Row) {
  await page.goto(url, { waitUntil: 'networkidle' })
  if (tab) await page.locator('.tabs .tab', { hasText: tab }).click()
  const row = page.locator(scroller).first()
  await expect(row).toBeVisible()
  await page.waitForTimeout(700)

  const room = await row.evaluate(el => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }))
  expect(room.scrollWidth, `${what} do not overflow here, so there is nothing to swipe`).toBeGreaterThan(room.clientWidth + 40)

  /* the first card sits at the row's start and is wholly on screen; the finger lands in its
     middle, which is exactly where a person's does */
  const box = (await page.locator(card).first().boundingBox())!
  await swipe(page, box.x + box.width / 2, box.y + box.height / 2, 300)

  await page.waitForTimeout(400)                           // the swipe's momentum and the snap, settled
  expect(await row.evaluate(el => el.scrollLeft)).toBeGreaterThan(40)
}

test.describe('a sideways row under a finger', () => {
  for (const row of [
    { what: 'the cards on Home', url: '/?nav=top&at=19:40', scroller: '.bento', card: '.bento .tile' },
    { what: "a room's cards", url: '/?nav=top&room=living&at=19:40', scroller: '.tiles', card: '.tiles > .tile' },
  ] as Row[]) {
    test(`${row.what} scroll when the finger lands on a card`, async ({ page }) => swipesUnderAFinger(page, row))
  }

  /* The one row that always worked, kept as the control. The mock house's five rooms fit inside
     1280, so this one is read on a narrower panel, where they do not. */
  test.describe('on a narrower panel', () => {
    test.use({ viewport: { width: 1024, height: 768 } })
    test('the rooms list scrolls when the finger lands on a room', async ({ page }) =>
      swipesUnderAFinger(page, { what: 'the rooms list', url: '/?nav=top&at=19:40', tab: 'Rooms', scroller: '.rooms-bento', card: '.rooms-bento > .room-cell' }))
  })
})
