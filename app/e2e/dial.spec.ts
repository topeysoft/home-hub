// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The thermostat card is the dial on the wall.

   art.ts has drawn a thermostat face since the device library was written, and until now no screen
   in the house showed it: `.bento .tile.climate .face-render` and
   `.tiles > .tile.climate[data-size='third'] .face-render` each set display:none, each with a note
   saying a dial did not survive the card it was given. Both were written when the row was shorter
   and when the dial was competing with two step buttons for the same space. The buttons are in the
   pane now, and design/nightfall page 3 has the card measured at both sizes the row produces.

   This is an e2e because the whole question is whether the drawing reaches the screen. Nothing that
   reads the stylesheet can see a rule five thousand lines away turning it off, and nothing that
   reads the source can see it either: `<DeviceArt>` is in ClimateTile's template whether or not any
   pixel of it is ever painted. */
import { expect, test, type Page } from '@playwright/test'

const card = (page: Page) =>
  page.evaluate(() => {
    const t = document.querySelector('.tile.climate')
    if (!t) return null
    const face = t.querySelector('.face-render')
    const box = face?.getBoundingClientRect()
    return {
      shown: face ? getComputedStyle(face).display : 'no .face-render in the markup',
      /* the arc is the one mark that says which way the house is going, and it is drawn by
         art.ts rather than by CSS -- if it is missing the drawing arrived empty */
      arc: !!t.querySelector('svg ellipse[stroke-dasharray], svg circle[stroke-dasharray]'),
      size: box ? Math.round(Math.min(box.width, box.height)) : 0,
      steps: [...t.querySelectorAll('.clim-btn')].filter(b => getComputedStyle(b).display !== 'none').length,
      reading: (t.querySelector('.clim-big') as HTMLElement | null)?.offsetHeight ?? 0,
    }
  })

test('the dial is on the card, and the temperature is not', async ({ page }) => {
  /* 1440x900 pinned: this is the size every board on design/nightfall page 3 is drawn at, and the
     project's own viewport is 1280x800 -- a real panel size, but not the one the pictures argue
     about. A spec that read whatever the project happened to be set to would be measuring the
     config rather than the card. */
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/?layout=wall&nav=top&at=20:10&wx=cloudy', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.climate')).toBeVisible()
  const c = (await card(page))!

  expect(c.shown).not.toBe('none')
  expect(c.arc).toBe(true)
  /* big enough to be the drawing rather than a token of one. The note that removed it said 92px
     with the reading pushed out of the card; this is the number that says we are not back there. */
  expect(c.size).toBeGreaterThan(120)
  /* and the reading is still a reading -- the dial must not have been bought by shrinking it */
  expect(c.reading).toBeGreaterThan(38)
  /* On a full-height wall the card carries the steps as well, UNDER the dial. Beside it is what
     every earlier attempt did and what cost the drawing its size: two 44px buttons and their gaps
     take 108 of the card's 217 usable width. Under it they cost 44 of a track that has it. */
  expect(c.steps).toBe(2)
})

/* The case both of the old notes were actually about. --row bottoms out on a short screen, and
   ClimateDial.dc.html says the dial survives 161x168; if that stops being true this is where it
   shows. */
test('and it survives the row at its floor', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 650 })
  await page.goto('/?layout=wall&nav=top&at=20:10&wx=cloudy', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.climate')).toBeVisible()
  const c = (await card(page))!

  expect(c.shown).not.toBe('none')
  expect(c.arc).toBe(true)
  expect(c.size).toBeGreaterThan(75)
  /* the reading has to stay readable from a doorway even here: the whole argument for taking the
     dial away the first time was that the number was worth more than the picture, and the answer
     is that at this size we keep both, not that we changed our mind about the number */
  expect(c.reading).toBeGreaterThan(22)
  /* and HERE the steps are the thing that gives. Measured with them still on the card, the dial
     runs 133px at 900, 103 at 800 and 53 at 700: the last is a token of a dial, not one. The
     temperature is a long press away instead. */
  expect(c.steps).toBe(0)
})

/* The line itself, because a threshold nobody checks drifts. The steps are kept while the dial can
   stay near 100px with them on the card, which is 800 of window -- including the 1280x800 this
   suite otherwise runs at. Below it the drawing gets the space back. */
test('the steps appear exactly while the dial can afford them', async ({ page }) => {
  for (const [height, steps] of [[900, 2], [800, 2], [799, 0], [700, 0]] as [number, number][]) {
    await page.setViewportSize({ width: 1440, height })
    await page.goto('/?layout=wall&nav=top&at=20:10&wx=cloudy', { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.climate')).toBeVisible()
    const c = (await card(page))!
    expect(c.steps, `at ${height}px tall`).toBe(steps)
    /* whichever side of the line, the drawing never falls to a token of one. 100 is the number the
       line is drawn at; the margin below is for the pixel either side of a media query. */
    expect(c.size, `dial at ${height}px tall`).toBeGreaterThan(95)
  }
})
