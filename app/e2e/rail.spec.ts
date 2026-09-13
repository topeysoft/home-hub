/* The rail: cards resolve as they arrive. A card fully on the rail is crisp, one off it is faded and
   blurred, and the ramp between never runs backwards. This is a scroll-driven animation done in CSS,
   so nothing in the app's own code would notice it breaking. */
import { expect, test, type Page } from '@playwright/test'

type Card = { index: number; visible: number; opacity: number; blur: number }

async function cards(page: Page, scrollLeft: number): Promise<Card[]> {
  await page.evaluate((s) => {
    const rail = document.querySelector('.bento') as HTMLElement
    rail.style.scrollSnapType = 'none'   // snap rounds every step to a card edge; a finger mid-swipe is between them
    rail.scrollLeft = s
  }, scrollLeft)
  await page.waitForTimeout(120)         // scroll-driven animations resolve on the next frame, not in this tick
  return page.evaluate(() => {
    const rail = document.querySelector('.bento')!, rr = rail.getBoundingClientRect()
    return [...rail.children].map((c, index) => {
      const b = c.getBoundingClientRect(), cs = getComputedStyle(c)
      return {
        index,
        visible: Math.max(0, Math.min(b.right, rr.right) - Math.max(b.left, rr.left)) / b.width,
        opacity: Number(cs.opacity),
        blur: Number(cs.filter.match(/blur\(([\d.]+)px\)/)?.[1] ?? 0),
      }
    })
  })
}

/* face=paper as well as layout=rail, and both matter. The numbers below -- .35 opacity, 6px of
   blur, both ends of the row softening the same amount -- are paper's even-handed edge fade. Glass
   replaces them with a focal plane, which is a different shape on purpose. Without pinning the
   face this spec passes or fails on whatever the house in the mock happens to be set to, which is
   how it started failing against a mock started with FACE=glass. */
test.beforeEach(async ({ page }) => {
  await page.goto('/?layout=rail&face=paper&at=19:40', { waitUntil: 'networkidle' })
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
  /* The behaviour the rail was tuned to: nearly in is still not in. Swept rather than sampled at one
     scroll position, because where a card lands depends on how wide the cards are, and a test that
     quietly finds nothing to look at is a test that passes without asking anything. */
  const nearly: Card[] = []
  for (let s = 0; s <= 700; s += 25) {
    nearly.push(...(await cards(page, s)).filter(c => c.visible > 0.85 && c.visible < 0.995))
  }
  expect(nearly.length, 'no card was ever caught nearly in').toBeGreaterThan(0)
  for (const c of nearly) {
    expect(c.opacity, `card ${c.index} at ${(c.visible * 100).toFixed(0)}% in`).toBeLessThan(1)
  }
})

test('the ramp never runs backwards as a card arrives', async ({ page }) => {
  /* Sweeping the rail, a card should only ever get more solid as more of it comes in. A ramp that
     dips is the kind of thing you see as a flicker and cannot describe.

     Followed one card at a time. Cards are not all the same width, so the fraction of one that is
     visible is not the same quantity as the fraction of another, and pooling them compares curves
     that were never the same curve. */
  const byCard = new Map<number, Card[]>()
  for (let s = 0; s <= 700; s += 35) {
    for (const c of await cards(page, s)) {
      if (c.visible > 0.01 && c.visible < 0.995) byCard.set(c.index, [...(byCard.get(c.index) ?? []), c])
    }
  }

  const arriving = [...byCard.values()].filter(samples => samples.length >= 4)
  expect(arriving.length, 'no card was caught arriving often enough to see its ramp').toBeGreaterThan(0)

  for (const samples of arriving) {
    const byVisible = [...samples].sort((a, b) => a.visible - b.visible)
    for (let i = 1; i < byVisible.length; i++) {
      const at = `card ${byVisible[i].index} at ${(byVisible[i].visible * 100).toFixed(0)}% in`
      expect(byVisible[i].opacity, `opacity, ${at}`).toBeGreaterThanOrEqual(byVisible[i - 1].opacity - 0.02)
      expect(byVisible[i].blur, `blur, ${at}`).toBeLessThanOrEqual(byVisible[i - 1].blur + 0.2)
    }
  }
})

test('the rail scrolls sideways and the page itself never does', async ({ page }) => {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})
