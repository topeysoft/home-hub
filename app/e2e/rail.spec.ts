/* The rail: cards resolve as they arrive. A card fully on the rail is crisp, one off it is faded and
   blurred, and the ramp between never runs backwards. This is a scroll-driven animation done in CSS,
   so nothing in the app's own code would notice it breaking. */
import { expect, test, type Page } from '@playwright/test'

type Card = { visible: number; opacity: number; blur: number }

async function cards(page: Page, scrollLeft: number): Promise<Card[]> {
  await page.evaluate((s) => {
    const rail = document.querySelector('.bento') as HTMLElement
    rail.style.scrollSnapType = 'none'   // snap rounds every step to a card edge; a finger mid-swipe is between them
    rail.scrollLeft = s
  }, scrollLeft)
  await page.waitForTimeout(120)         // scroll-driven animations resolve on the next frame, not in this tick
  return page.evaluate(() => {
    const rail = document.querySelector('.bento')!, rr = rail.getBoundingClientRect()
    return [...rail.children].map((c) => {
      const b = c.getBoundingClientRect(), cs = getComputedStyle(c)
      return {
        visible: Math.max(0, Math.min(b.right, rr.right) - Math.max(b.left, rr.left)) / b.width,
        opacity: Number(cs.opacity),
        blur: Number(cs.filter.match(/blur\(([\d.]+)px\)/)?.[1] ?? 0),
      }
    })
  })
}

test.beforeEach(async ({ page }) => {
  await page.goto('/?layout=rail&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento-card').first()).toBeVisible()
  await page.waitForTimeout(700)
})

test('the browser can actually run the effect this depends on', async ({ page }) => {
  // If this ever goes false the cards would sit at one value and the rail would look broken, quietly.
  expect(await page.evaluate(() => CSS.supports('animation-timeline: view()'))).toBe(true)
})

test('a card fully on the rail is completely crisp', async ({ page }) => {
  for (const c of (await cards(page, 0)).filter(c => c.visible > 0.999)) {
    expect(c.opacity).toBeCloseTo(1, 2)
    expect(c.blur).toBeCloseTo(0, 1)
  }
})

test('a card still off the rail is faded and blurred rather than half-drawn', async ({ page }) => {
  for (const c of (await cards(page, 0)).filter(c => c.visible === 0)) {
    expect(c.opacity).toBeLessThan(0.5)
    expect(c.blur).toBeGreaterThan(3)
  }
})

test('a card only becomes crisp once it is all the way in', async ({ page }) => {
  // The behaviour the rail was tuned to: nearly in is still not in.
  const nearly = (await cards(page, 300)).filter(c => c.visible > 0.85 && c.visible < 0.999)
  test.skip(!nearly.length, 'no card was caught nearly in at this scroll position')
  for (const c of nearly) expect(c.opacity).toBeLessThan(1)
})

test('the ramp never runs backwards as a card arrives', async ({ page }) => {
  /* Sweeping the rail, the card straddling the right edge should only ever get more solid as more of
     it comes in. A ramp that dips is the kind of thing you see as a flicker and cannot describe. */
  const seen: Card[] = []
  for (let s = 0; s <= 700; s += 35) {
    const rail = await cards(page, s)
    const arriving = rail.find(c => c.visible > 0.01 && c.visible < 0.99)
    if (arriving) seen.push(arriving)
  }
  expect(seen.length).toBeGreaterThan(3)

  const byVisible = [...seen].sort((a, b) => a.visible - b.visible)
  for (let i = 1; i < byVisible.length; i++) {
    expect(byVisible[i].opacity, `opacity at ${byVisible[i].visible}`).toBeGreaterThanOrEqual(byVisible[i - 1].opacity - 0.02)
    expect(byVisible[i].blur, `blur at ${byVisible[i].visible}`).toBeLessThanOrEqual(byVisible[i - 1].blur + 0.2)
  }
})

test('the rail scrolls sideways and the page itself never does', async ({ page }) => {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})
