// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Move 6 of the eight -- the house listening -- and the first of them that is a STATE rather than a
   passage. That is the whole of what is checked here.

   A tap has no letting go, so the orb has to hold 1.18 for as long as somebody is talking, and the
   ring is the mark at the end rather than a pulse throughout. Both halves break silently: a held
   scale that is really a 320ms animation looks identical for its first third, and a ring that is
   left as a state instead of taken off looks identical until the second sentence, which then gets
   no ring at all. So the orb is sampled per frame, the way move 7's box is in say.spec.ts -- these
   are shorter than the time it takes to screenshot them. */
import { expect, test, type Page } from '@playwright/test'

const WALL = '/?face=glass&layout=wall&nav=top&at=19:40'

/** the orb's scale and the ring, frame by frame, while `during` happens */
async function trace(page: Page, during: () => Promise<void>, ms = 900) {
  await page.evaluate((dur) => {
    const w = window as any
    w.__frames = []
    const t0 = performance.now()
    const scaleOf = (el: Element | null) => {
      if (!el) return null
      const m = new DOMMatrixReadOnly(getComputedStyle(el).transform)
      return Math.round(m.a * 1000) / 1000
    }
    const tick = () => {
      const ring = document.querySelector('.say-ring')
      w.__frames.push({
        t: performance.now() - t0,
        orb: scaleOf(document.querySelector('.say-orb')),
        ring: ring ? scaleOf(ring) : null,
        ringO: ring ? Number(getComputedStyle(ring).opacity) : null,
      })
      if (performance.now() - t0 < dur) requestAnimationFrame(tick)
    }
    tick()
  }, ms)
  await during()
  await page.waitForTimeout(ms + 60)
  return page.evaluate(
    () => (window as any).__frames as { t: number; orb: number | null; ring: number | null; ringO: number | null }[],
  )
}

const tapTheOrb = (page: Page) =>
  page.evaluate(() => {
    document.querySelector('.say-box')!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })

const hear = (page: Page, said: string) => page.evaluate((s) => (window as any).__hear(s), said)

test.describe('a panel with nothing to listen with, which is every panel today', () => {
  test('a tap on the orb opens the box to type in, exactly as it always has', async ({ page }) => {
    await page.goto(WALL, { waitUntil: 'networkidle' })
    await expect(page.locator('.say-box')).toBeVisible()
    await page.waitForTimeout(600)
    const rest = (await page.locator('.say-box').boundingBox())!.width
    await tapTheOrb(page)
    await page.waitForTimeout(700)
    expect((await page.locator('.say-box').boundingBox())!.width, 'the box did not open').toBeGreaterThan(rest * 4)
    await expect(page.locator('.say')).not.toHaveClass(/listening/)
    expect(await page.locator('.say-orb').evaluate((el) => getComputedStyle(el).transform)).toBe('none')
  })
})

test.describe('a panel that can hear', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${WALL}&listen=1`, { waitUntil: 'networkidle' })
    await expect(page.locator('.say-box')).toBeVisible()
    await page.waitForTimeout(600)
  })

  test('the orb rises to 1.18 and HOLDS there, for as long as somebody is talking', async ({ page }) => {
    const frames = await trace(page, () => tapTheOrb(page))
    const top = Math.max(...frames.map((f) => f.orb ?? 0))
    expect(top, `the orb never rose (peak ${top})`).toBeGreaterThan(1.17)
    expect(top, "the orb went past the board's 1.18").toBeLessThan(1.19)
    // and it is still up at the end, which is what makes it a state and not a passage
    expect(frames[frames.length - 1].orb, 'the orb came back down on its own').toBeGreaterThan(1.17)
    await expect(page.locator('.say')).toHaveClass(/listening/)
    await expect(page.locator('.say-hint')).toBeVisible()
    await expect(page.locator('.say-hint')).toHaveText('Listening…')
  })

  test('a sentence lands: one ring, once, and the orb comes home', async ({ page }) => {
    await tapTheOrb(page)
    await page.waitForTimeout(400)
    const frames = await trace(page, () => hear(page, 'kitchen lights off'))
    const rings = frames.filter((f) => f.ring !== null)
    expect(rings.length, 'no ring was drawn').toBeGreaterThan(4)
    expect(Math.min(...rings.map((f) => f.ring!)), 'the ring did not start inside the orb').toBeLessThan(1)
    expect(Math.max(...rings.map((f) => f.ring!)), "the ring did not reach the board's 2.2").toBeGreaterThan(2.1)
    expect(Math.max(...rings.map((f) => f.ringO!)), 'the ring never came up to .55').toBeGreaterThan(0.4)
    // once: it is taken off again, so the next sentence gets a ring of its own
    expect(frames[frames.length - 1].ring, 'the ring was left on the screen').toBeNull()
    expect(frames[frames.length - 1].orb, 'the orb stayed up after the sentence landed').toBeLessThan(1.02)
    await expect(page.locator('.say')).not.toHaveClass(/listening/)
  })

  test('a second tap is how you stop, and nothing is left listening', async ({ page }) => {
    await tapTheOrb(page)
    await expect(page.locator('.say')).toHaveClass(/listening/)
    await tapTheOrb(page)
    await page.waitForTimeout(700)
    await expect(page.locator('.say')).not.toHaveClass(/listening/)
    expect(Number(await page.locator('.say-orb').evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).a))).toBeLessThan(1.02)
  })
})

test.describe('asked not to move', () => {
  test.use({ reducedMotion: 'reduce' })

  test('the house still says it is listening, and says it in words', async ({ page }) => {
    await page.goto(`${WALL}&listen=1`, { waitUntil: 'networkidle' })
    await expect(page.locator('.say-box')).toBeVisible()
    await page.waitForTimeout(600)
    await tapTheOrb(page)
    await page.waitForTimeout(500)
    /* the held state is the one move of the eight that cannot collapse to a fade -- it persists, so
       under reduced motion it has to SAY the house is listening without moving to do it */
    await expect(page.locator('.say-hint')).toBeVisible()
    await expect(page.locator('.say-hint')).toHaveText('Listening…')
    expect(await page.locator('.say-orb').evaluate((el) => getComputedStyle(el).transform)).toBe('none')
  })
})
