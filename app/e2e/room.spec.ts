// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A room, arranged.

   A room does not scroll DOWN. It fills in columns and runs off to the right when there is more of it
   than fits, and that is what keeps the way back on the screen: the only axis that moves is one the
   head does not sit on. Before this, the living room overflowed by 376px and scrolling to the bottom
   put the back button at y -264 -- gone, on a wall panel with no keyboard and no Escape.

   Everything here is measured in a real browser at the size the panel is actually read at, because
   none of it can be seen in the stylesheet: whether a grid overflows is a fact about the content. */
import { expect, test, type Page } from '@playwright/test'

const at = (room: string) => `/?room=${room}&nav=top&at=19:40`

async function room(page: Page, id: string) {
  await page.goto(at(id), { waitUntil: 'networkidle' })
  await expect(page.locator('.tiles > .tile').first()).toBeVisible()
  await page.waitForTimeout(700)
}

const geometry = (page: Page) => page.evaluate(() => {
  const doc = document.scrollingElement!
  const stage = document.querySelector('.stage')!
  const grid = document.querySelector('.tiles')!
  const back = document.querySelector('.back')!.getBoundingClientRect()
  return {
    pageY: doc.scrollHeight - doc.clientHeight,
    stageY: stage.scrollHeight - stage.clientHeight,
    gridY: grid.scrollHeight - grid.clientHeight,
    gridX: grid.scrollWidth - grid.clientWidth,
    back: { x: Math.round(back.x), y: Math.round(back.y) },
    sizes: [...document.querySelectorAll('.tiles > .tile')].map((t) => t.getAttribute('data-size')),
    columns: new Set([...document.querySelectorAll('.tiles > .tile')]
      .map((t) => Math.round(t.getBoundingClientRect().x))).size,
  }
})

/* The three rooms the mock house actually has: four devices, four devices, and the seven-device
   living room that was the only one overflowing. */
for (const id of ['living', 'kitchen', 'bedroom']) {
  test(`the ${id} is a screen, not a scroller`, async ({ page }) => {
    await room(page, id)
    const g = await geometry(page)
    expect(g.pageY, `the ${id} scrolls the page down by ${g.pageY}px`).toBe(0)
    expect(g.stageY, `the ${id} scrolls the stage down by ${g.stageY}px`).toBe(0)
    expect(g.gridY, `the ${id}'s grid scrolls down by ${g.gridY}px`).toBe(0)
    // three heights and nothing else -- a fourth would mean a tile placed itself
    for (const s of g.sizes) expect(['full', 'half', 'third']).toContain(s)
  })
}

/* The defect this whole arrangement exists to remove. Sweeping to the far end of a room must not move
   the way out of it, and it cannot, because the way out is not on the axis that moves. */
test('the way back does not move, however far the room is swept', async ({ page }) => {
  await room(page, 'living')
  const before = await geometry(page)

  await page.evaluate(() => {
    const g = document.querySelector('.tiles')!
    g.scrollLeft = g.scrollWidth              // as far right as the room goes
  })
  await page.waitForTimeout(500)
  const after = await geometry(page)

  expect(after.back, 'the way out of the room moved when the room was swept').toEqual(before.back)
  expect(after.back.y, 'the way out of the room is off the top of the screen').toBeGreaterThan(0)
  expect(after.back.x, 'the way out of the room is off the left of the screen').toBeGreaterThan(0)
})

/* The arrangement is decided on the way in and then held.
   Ranked live, turning the main lamp off promoted the next-brightest one, resized both and reflowed
   every column -- so the tiles moved under the finger that had just tapped them, and a second tap in
   the same place reached a different device. This is that, as a test: tap a light, and everything
   else on the screen has to still be where it was. */
test('switching something off does not rearrange the room around it', async ({ page }) => {
  await room(page, 'living')
  const where = () => page.evaluate(() => [...document.querySelectorAll('.tiles > .tile')]
    .map((t) => {
      const b = t.getBoundingClientRect()
      return `${t.className.split(' ').slice(0, 2).join('.')}@${Math.round(b.x)},${Math.round(b.y)}:${t.getAttribute('data-size')}`
    }))

  const before = await where()
  const lamp = page.locator('.tile.light').first()
  const state = lamp.locator('.tile-state')
  const was = await state.innerText()

  const box = (await lamp.boundingBox())!
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect(state).not.toHaveText(was, { timeout: 3000 })

  expect(await where(), 'a lamp changing state moved the tiles around it').toEqual(before)

  // and the same place still reaches the same device, which is the point of holding the plan
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect(state).toHaveText(was, { timeout: 3000 })
})

/* A phone is tall, not wide. The sideways sweep is a wall gesture and it inverts below 860, the same
   breakpoint the Home rail already turns at -- pointing a phone at a horizontal sweep would be
   teaching the wrong gesture on the one screen where there is no room for it. */
test('on a phone the room is a column again', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await room(page, 'living')
  const g = await page.evaluate(() => {
    const grid = document.querySelector('.tiles')!
    const doc = document.scrollingElement!
    const stage = document.querySelector('.stage')!
    return {
      flow: getComputedStyle(grid).gridAutoFlow,
      gridX: grid.scrollWidth - grid.clientWidth,
      pageX: doc.scrollWidth - doc.clientWidth,
      // on a phone the STAGE is the scroller, not the document -- the shell is still a fixed app frame
      scrollsDown: (stage.scrollHeight - stage.clientHeight) + (doc.scrollHeight - doc.clientHeight),
    }
  })
  expect(g.flow, 'a phone is still filling in columns').toContain('row')
  expect(g.gridX, 'the room still sweeps sideways on a phone').toBe(0)
  expect(g.pageX, 'the page scrolls sideways on a phone').toBe(0)
  expect(g.scrollsDown, 'a phone room does not scroll down, so it is hiding devices').toBeGreaterThan(0)
})
