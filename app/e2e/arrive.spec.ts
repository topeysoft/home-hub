/* The Rooms and Cameras tabs arrive, the way Home's row always has.
 *
 * Sampled every frame from inside the page, because the move is faster than a
 * screenshot: a card held off its place for a few frames and then let in leaves
 * nothing behind to assert afterwards. What each test reads is `translate` --
 * not a bounding box, which also moves when the page merely lays out.
 *
 * The two travel differently on purpose and the specs say which: the house runs
 * off the right edge so it comes in from there, and the cameras are a grid that
 * wraps downwards so they come up from below. See src/arrive.ts and the block
 * at the end of panel.css. */
import { expect, test, type Page } from '@playwright/test'

type Frame = { t: number; op: string; tr: (string | null)[] }

/** Sample the container's opacity and its first four children's travel, every frame. */
async function watch(page: Page, box: string, item: string) {
  const seen: Frame[] = []
  await page.exposeFunction('__frame', (f: Frame) => { seen.push(f) })
  await page.addInitScript(([box, item]) => {
    const tick = () => {
      const el = document.querySelector(box)
      if (el) (window as any).__frame({
        t: Math.round(performance.now()),
        op: Number(getComputedStyle(el).opacity).toFixed(2),
        tr: [...el.querySelectorAll(':scope > ' + item)].slice(0, 4).map((c) => getComputedStyle(c).translate),
      })
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }, [box, item] as const)
  return seen
}

const px = (v: string | null | undefined) =>
  !v || v === 'none' ? 0 : Math.abs(parseFloat(v)) + Math.abs(parseFloat(v.split(' ')[1] ?? '0'))
/** the last moment card `i` was still off its place */
const homeAt = (seen: Frame[], i: number) => seen.reduce((t, f) => (px(f.tr[i]) > 0.5 ? f.t : t), 0)

async function openTab(page: Page, name: RegExp) {
  await page.goto('/?nav=top&at=19:40', { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)
  await page.getByRole('button', { name }).click()
  await page.waitForTimeout(1700) // past the last card's wait plus its travel, and past the settle
}

test('the house arrives from the side it runs off, one card after another', async ({ page }) => {
  const seen = await watch(page, '.rooms-bento', '.room-cell')
  await openTab(page, /^Rooms$/)

  expect(seen.some((f) => f.op === '0.00'), 'the tab never faded in; it was just suddenly there').toBe(true)
  expect(seen[seen.length - 1].op, 'the tab never finished arriving').toBe('1.00')
  // in from the right, which is the way the columns run off the screen
  expect(Math.max(...seen.map((f) => px(f.tr[0]))), 'no card ever travelled').toBeGreaterThan(100)
  // and one after another rather than all together
  expect(homeAt(seen, 3) - homeAt(seen, 0), 'the cards arrived as one block, not staggered').toBeGreaterThan(80)
  // nothing is left on a card once it is home: a held card and a press must behave
  // as if this had never happened
  const cell = page.locator('.room-cell').first()
  expect(await cell.evaluate((el) => getComputedStyle(el).translate)).toBe('none')
  await expect(page.locator('.rooms-bento')).not.toHaveClass(/\b(set|go)\b/)
})

test('the cameras come up from below, because nothing on that tab sweeps', async ({ page }) => {
  const seen = await watch(page, '.cameras-all', '.tile.camera')
  await openTab(page, /^Cameras$/)

  expect(seen.some((f) => f.op === '0.00'), 'the tab never faded in').toBe(true)
  expect(seen[seen.length - 1].op, 'the tab never finished arriving').toBe('1.00')
  // a lift, not a sweep: a grid that wraps downwards has no sideways gesture to teach
  const worst = Math.max(...seen.map((f) => px(f.tr[0])))
  expect(worst, 'no camera ever travelled').toBeGreaterThan(8)
  expect(worst, 'a camera travelled a sweep worth of distance, on a tab that does not sweep').toBeLessThan(200)
  expect(homeAt(seen, 2) - homeAt(seen, 0), 'the cameras arrived as one block, not staggered').toBeGreaterThan(40)
})

test.describe('asked not to move', () => {
  test.use({ reducedMotion: 'reduce' })

  test('both tabs still arrive, as the fade every move collapses to', async ({ page }) => {
    for (const [tab, box, item] of [[/^Rooms$/, '.rooms-bento', '.room-cell'], [/^Cameras$/, '.cameras-all', '.tile.camera']] as const) {
      const ctx = await page.context().newPage()
      const seen: Frame[] = []
      await ctx.exposeFunction('__frame', (f: Frame) => { seen.push(f) })
      await ctx.addInitScript(([box, item]) => {
        const tick = () => {
          const el = document.querySelector(box)
          if (el) (window as any).__frame({
            t: Math.round(performance.now()),
            op: Number(getComputedStyle(el).opacity).toFixed(2),
            tr: [...el.querySelectorAll(':scope > ' + item)].slice(0, 4).map((c) => getComputedStyle(c).translate),
          })
          requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }, [box, item] as const)
      await ctx.goto('/?nav=top&at=19:40', { waitUntil: 'networkidle' })
      await ctx.waitForTimeout(700)
      await ctx.getByRole('button', { name: tab }).click()
      await ctx.waitForTimeout(1200)

      // it still arrives rather than appearing between two frames
      expect(seen.some((f) => f.op === '0.00'), `${box} was just suddenly there`).toBe(true)
      expect(seen[seen.length - 1].op, `${box} never finished arriving`).toBe('1.00')
      // and nothing travelled on the way. One painted frame off its place is the move
      // this is here to remove, whether or not a transition was carrying it.
      const travelled = seen.filter((f) => f.tr.some((v) => px(v) > 0.5))
      expect(travelled.length, `${box} travelled: ${travelled[0]?.tr.join()}`).toBe(0)
      await ctx.close()
    }
  })
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the house does not sweep in, because at this width it does not sweep', async ({ page }) => {
    const seen = await watch(page, '.rooms-bento', '.room-cell')
    await openTab(page, /^Rooms$/)

    expect(seen.some((f) => f.op === '0.00'), 'the tab never faded in').toBe(true)
    const travelled = seen.filter((f) => f.tr.some((v) => px(v) > 0.5))
    expect(travelled.length, `a card swept in on a phone: ${travelled[0]?.tr.join()}`).toBe(0)
  })
})
