/* Wall: the weather large on the left, and what is on beside it.

   The arrangement is the whole of this layout, so that is what gets asserted -- where things are
   relative to each other, not what they look like. Two of these would pass under Rail as well; the
   ones that matter are that the weather is BESIDE the row rather than above it, and that the row is
   taller here, which is what the greeting's absence buys. */
import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/?layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento').first()).toBeVisible()
  await page.waitForTimeout(1500)                 // past the row's arrival
})

test('the house is set to it, and it is its own arrangement', async ({ page }) => {
  expect(await page.getAttribute('.shell', 'data-layout')).toBe('wall')
  await expect(page.locator('.wall-home')).toHaveCount(1)
  await expect(page.locator('.rail-home')).toHaveCount(0)
})

test('there is no greeting taking the top of the screen', async ({ page }) => {
  // the thing Wall is: the row starts near the top because nothing is above it but the bar
  await expect(page.locator('.rail-greet')).toHaveCount(0)
  const row = (await page.locator('.bento').boundingBox())!
  const bar = (await page.locator('.topbar').boundingBox())!
  expect(row.y - (bar.y + bar.height), 'something is sitting between the bar and the row')
    .toBeLessThan(180)
})

test('the weather is beside the row, not above it', async ({ page }) => {
  const wx = (await page.locator('.wall-wx').boundingBox())!
  const row = (await page.locator('.bento').boundingBox())!
  expect(wx.x + wx.width, 'the weather overlaps the row').toBeLessThanOrEqual(row.x + 1)
  // and it is actually large: the board gives it just under a third of the screen
  expect(wx.width).toBeGreaterThan(260)
  expect(wx.height).toBeGreaterThan(380)
  // the pane hangs in front of the drawing rather than sitting under it
  const art = (await page.locator('.wall-cloud').boundingBox())!
  const loz = (await page.locator('.wall-loz').boundingBox())!
  expect(loz.x, 'the pane is not in front of the drawing at all').toBeLessThan(art.x + art.width)
  expect(loz.x, 'the pane covers the drawing instead of overlapping it').toBeGreaterThan(art.x)
})

test('the row is taller than the rail can afford', async ({ page }) => {
  const wall = (await page.locator('.bento').boundingBox())!.height
  await page.goto('/?layout=rail&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento').first()).toBeVisible()
  await page.waitForTimeout(1500)
  const rail = (await page.locator('.bento').boundingBox())!.height
  expect(wall, `wall ${wall} is not taller than rail ${rail}`).toBeGreaterThan(rail + 40)
})

test('it still carries everything Home must carry', async ({ page }) => {
  // layout.ts is explicit that these are not negotiable per-layout: the command box, anything
  // asking to be let in, the nudges, and Needs a look. A layout that drops one strands somebody.
  await expect(page.locator('.bottombar .say-box'), 'no way to tell the house anything').toHaveCount(1)
  await expect(page.locator('.nudges'), 'nowhere for an update or a found device to be offered').toHaveCount(1)
})

/* The two constants this layout brings with it. Wall is the only arrangement allowed any, so the
   half of this that matters is the second half: that Rail is standing exactly where it was. A
   typeface that leaked would not look like a bug, it would look like a redesign. */
test('it brings its own type and corners, and leaves the other arrangements where they were', async ({ page }) => {
  const look = () => page.evaluate(async () => {
    await document.fonts.ready
    const card = document.querySelector('.bento .tile')!
    const asked = getComputedStyle(document.querySelector('.shell')!).fontFamily.split(',')[0].replace(/['"]/g, '')
    return {
      asked,
      // asking for a face the browser does not have is the same as not asking
      loaded: document.fonts.check(`16px "${asked}"`),
      radius: getComputedStyle(card).borderRadius,
    }
  })

  const wall = await look()
  expect(wall.asked, 'Wall is not in its own typeface').toBe('Plus Jakarta Sans Variable')
  expect(wall.loaded, 'the typeface was asked for but never loaded, so this is the fallback').toBe(true)
  expect(wall.radius).toBe('28px')

  await page.goto('/?layout=rail&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento').first()).toBeVisible()
  await page.waitForTimeout(800)
  const rail = await look()
  expect(rail.asked, "Wall's typeface leaked into the Rail").toBe('Instrument Sans Variable')
  expect(rail.radius, "Wall's corners leaked into the Rail").toBe('26px')
})

/* Measured against the board rather than eyeballed. design/nightfall/Main.dc.html is 1440x900, so
   every number here is a share of the screen and holds at any size. The cards keep the proportions
   they were drawn at, which means their widths follow the row's height: the Rail's card lands near
   square and the board's is portrait, and a panel read from across a room wants portrait, because
   more of the house fits on it. */
test('the row is proportioned the way the board draws it', async ({ page }) => {
  const W = 1280, H = 800
  const box = async (sel: string, nth = 0) => {
    const b = (await page.locator(sel).nth(nth).boundingBox())!
    return { x: b.x / W, y: b.y / H, w: b.width / W, h: b.height / H }
  }
  const near = (got: number, want: number, what: string) =>
    expect(Math.abs(got - want), `${what}: ${(got * 100).toFixed(1)}% against the board's ${(want * 100).toFixed(1)}%`)
      .toBeLessThan(0.015)

  // what is playing: 332x548 of 1440x900
  const media = await box('.bento-card')
  near(media.x, 506 / 1440, 'the first card starts in the wrong place')
  near(media.w, 332 / 1440, 'what is playing is the wrong width')
  near(media.h, 548 / 900, 'what is playing is the wrong height')

  // the glance column: two 252-wide cards where one tall card would be
  const glance = await box('.bento-card', 1)
  near(glance.x, 860 / 1440, 'the glance column starts in the wrong place')
  near(glance.w, 252 / 1440, 'a glance card is the wrong width')

  // the weather: 460 wide of 1440, and the pane 226x372 hung inside it
  // where the weather stops and the row starts, rather than the column's own width: the board's
  // block begins at the screen edge and the app's begins at the stage's padding, so the two
  // widths are not the same measurement even when the edge between them is in the same place
  const wx = await box('.wall-wx')
  near(wx.x + wx.w, 484 / 1440, 'the weather gives way to the row in the wrong place')
  const loz = await box('.wall-loz')
  near(loz.w, 226 / 1440, 'the pane is the wrong width')
  near(loz.h, 372 / 900, 'the pane is the wrong height')
})

/* The weather recedes with the row. It is not in the rail -- it is not in the house -- so it does
   not travel; it goes out of focus and the reading goes altogether, because a temperature you have
   swiped away from is not the thing you are reading any more. Without this the left third stays
   sharp while everything else moves, and reads as fixed furniture the cards are sliding behind.

   The last assertion is the one that would be easy to lose: the blur goes on the drawing and on the
   pane, never on the column holding both. A filter there forms a backdrop root and the pane's own
   frost dies with it -- the same trap as the rail's cards and the pane over the room. */
test('the weather recedes when the row is swiped away from home, whichever face is on', async ({ page }) => {
  const look = () => page.evaluate(() => {
    const g = (sel: string) => {
      const cs = getComputedStyle(document.querySelector(sel)!)
      return {
        blur: Number(cs.filter.match(/blur\(([\d.]+)px\)/)?.[1] ?? 0),
        opacity: Number(Number(cs.opacity).toFixed(2)),
        frost: (cs.getPropertyValue('backdrop-filter') || cs.getPropertyValue('-webkit-backdrop-filter') || 'none') !== 'none',
      }
    }
    return { drawing: g('.wall-cloud'), readout: g('.wall-loz'), column: g('.wall-wx') }
  })

  const swipe = async (to: number) => {
    await page.evaluate((x) => {
      const row = document.querySelector('.bento') as HTMLElement
      row.style.scrollSnapType = 'none'   // a snap would round the scroll to a card edge mid-measurement
      row.scrollLeft = x ? row.querySelector('.bento-card')!.getBoundingClientRect().width + 18 : 0
    }, to)
    await page.waitForTimeout(900)        // the recede is 650ms
  }

  for (const face of ['paper', 'glass']) {
    await page.goto(`/?layout=wall&nav=top&face=${face}&at=19:40`, { waitUntil: 'networkidle' })
    await expect(page.locator('.bento').first()).toBeVisible()
    await page.waitForTimeout(1500)

    const home = await look()
    expect(home.drawing.blur, `${face}: the weather is soft before anything has been swiped`).toBe(0)
    expect(home.readout.opacity, `${face}: the reading is not there to begin with`).toBe(1)

    await swipe(1)
    const away = await look()
    // whether it recedes is the layout's; how it recedes is the face's
    expect(away.drawing.opacity, `${face}: the drawing did not dim`).toBeLessThan(0.9)
    expect(away.readout.opacity, `${face}: the reading is still being offered for a sky you swiped past`).toBe(0)
    if (face === 'glass') {
      expect(away.drawing.blur, 'glass: the drawing stayed sharp while the row moved').toBeGreaterThan(4)
      expect(away.column.blur, "glass: the blur went on the column, which kills the pane's own frost").toBe(0)
      expect(away.readout.frost, 'glass: the pane lost its frost as it receded').toBe(true)
    } else {
      expect(away.drawing.blur, 'paper: a blur outside the row is a depth paper does not have').toBe(0)
    }

    await swipe(0)
    const back = await look()
    expect(back.drawing.blur, `${face}: the weather never came back into focus`).toBe(0)
    expect(back.readout.opacity, `${face}: the reading never came back`).toBe(1)
  }
})
