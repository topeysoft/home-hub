/* The command box, at rest and opened -- move 7 of the eight in design/nightfall.

   The claim under test is an ORDER, not a set of durations: width leads and the words follow, so
   the box is already the right size by the time there is anything to read in it, and on the way
   back the words go first and the width follows them home. Durations are load-dependent -- a frame
   on this panel runs about 25ms while glass is being painted -- so what is asserted is which of
   the two is ahead of the other, which is the thing that breaks silently when someone shortens a
   delay. Every number here is sampled per frame in the page, because these moves are shorter than
   the time it takes to screenshot them. */
import { expect, test, type Page } from '@playwright/test'

const WALL = '/?face=glass&layout=wall&nav=top&at=19:40'

/* the box and the words, frame by frame, while `move` is happening */
async function trace(page: Page, move: 'open' | 'shut', ms = 900) {
  return page.evaluate(
    ([which, dur]) =>
      new Promise<{ t: number; w: number; o: number }[]>((done) => {
        const box = document.querySelector('.say-box') as HTMLElement
        const input = box.querySelector('input') as HTMLInputElement
        const out: { t: number; w: number; o: number }[] = []
        const t0 = performance.now()
        if (which === 'open') box.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        else input.blur()
        const tick = () => {
          out.push({
            t: performance.now() - t0,
            w: box.getBoundingClientRect().width,
            o: Number(getComputedStyle(input).opacity),
          })
          if (performance.now() - t0 < (dur as number)) requestAnimationFrame(tick)
          else done(out)
        }
        tick()
      }),
    [move, ms] as const,
  )
}

test.beforeEach(async ({ page }) => {
  await page.goto(WALL, { waitUntil: 'networkidle' })
  await expect(page.locator('.say-box')).toBeVisible()
  await page.waitForTimeout(600)
})

test('at rest the box is only its orb', async ({ page }) => {
  const box = (await page.locator('.say-box').boundingBox())!
  const orb = (await page.locator('.say-orb').boundingBox())!
  // a circle: the pill is the orb and its collar, nothing else
  expect(Math.abs(box.width - box.height), 'the resting box is not round').toBeLessThan(2)
  expect(orb.width).toBeGreaterThan(box.width * 0.7)
  // and the orb is centred in it, which is what says the collar is even
  expect(Math.abs(orb.x - box.x - (box.x + box.width - orb.x - orb.width))).toBeLessThan(2)
})

test('a touch opens it: the width leads and the words follow', async ({ page }) => {
  const frames = await trace(page, 'open')
  const rest = frames[0].w
  const wide = frames[frames.length - 1].w
  expect(wide, 'the box never opened').toBeGreaterThan(rest * 4)

  // the frame the words first show on: by then the box is nearly the size it is going to be
  const words = frames.find((f) => f.o > 0.02)
  expect(words, 'the words never arrived').toBeTruthy()
  const through = (words!.w - rest) / (wide - rest)
  expect(through, `the words started ${(through * 100).toFixed(0)}% through the width`)
    .toBeGreaterThan(0.7)

  // and they arrive inside the box's own move rather than trailing along after it: the words are
  // 180ms behind a 460ms width and take 260, so the two land together within a frame or two
  const full = frames.find((f) => f.o > 0.99)!
  const home = frames.find((f) => f.w > wide - 1)!
  expect(full.t - home.t, 'the words are still arriving after the box has stopped').toBeLessThan(150)
})

test('and shuts again the other way round: the words go first', async ({ page }) => {
  await page.locator('.say-box input').focus()
  await page.waitForTimeout(800)
  const frames = await trace(page, 'shut')
  const wide = frames[0].w
  const rest = frames[frames.length - 1].w
  expect(rest, 'the box never shut').toBeLessThan(wide * 0.2)

  // The 180ms is gone, which is the whole of the claim: the words are already leaving by the time
  // the width has done a fifth of its travel, where on the way in they had not started at 70%.
  const early = frames.find((f) => (wide - f.w) / (wide - rest) > 0.2)!
  expect(early.o, 'the words waited for the width on the way back').toBeLessThan(0.9)

  // and they are gone well before the box is, so nothing is ever printed on a pill too small for it
  const gone = frames.find((f) => f.o < 0.02)!
  const home = frames.find((f) => f.w < rest + 1)!
  expect(gone.t, 'the box got home before its words had left').toBeLessThan(home.t)
})

test('it does not shut on a sentence somebody is still typing', async ({ page }) => {
  await page.locator('.say-box input').fill('kitchen lights off')
  await page.locator('.say-box input').blur()
  await page.waitForTimeout(700)
  const box = (await page.locator('.say-box').boundingBox())!
  expect(box.width, 'the box shut with a sentence in it').toBeGreaterThan(box.height * 4)
})

/* The strand, which layout.ts says is not negotiable per-face: the command box has to be there in
   every arrangement and every face. At rest it is an orb, but the input behind it never leaves the
   tab order, and reaching it is what opens the box -- so a keyboard never meets a shut one. */
test('the box is still the command box when it is resting', async ({ page }) => {
  await page.locator('.say-box input').focus()
  await page.waitForTimeout(700)
  await expect(page.locator('.say')).toHaveClass(/(^|\s)open(\s|$)/)
  const box = (await page.locator('.say-box').boundingBox())!
  expect(box.width).toBeGreaterThan(box.height * 4)
  await expect(page.locator('.say-box input')).toBeFocused()
})

/* The half that matters, and it is the same half every slice of this port has carried: paper is
   untouched. The move is the face's, so under paper the whole box is there from the start. */
test('paper keeps the whole box', async ({ page }) => {
  await page.goto('/?face=paper&layout=wall&nav=top&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.say-box')).toBeVisible()
  await page.waitForTimeout(400)
  const box = (await page.locator('.say-box').boundingBox())!
  expect(box.width, 'paper has learnt the move').toBeGreaterThan(box.height * 4)
  expect(await page.locator('.say-box input').evaluate((e) => getComputedStyle(e).opacity)).toBe('1')
})
