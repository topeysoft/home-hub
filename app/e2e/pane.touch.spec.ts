/* Every instrument in an opened device, used with a finger.
 *
 * A mouse pass proves less than it looks like here: these controls are dragged, and a drag on a
 * touch screen is the browser's own gesture until the element says otherwise — a control that
 * misses `touch-action: none` scrolls the pane instead of moving, and a control with no pointer
 * handler at all (which is what the thermostat's ring shipped as) simply does nothing while every
 * button beside it works. Both failures look perfectly fine in a screenshot.
 *
 * Touch goes through CDP, the path a real finger takes.
 */
import { expect, test, type Page } from '@playwright/test'

/** Where a control is, once a finger could actually reach it: on a narrow screen the pane scrolls,
    and half these controls start below the fold. */
async function boxOf(page: Page, selector: string) {
  const el = page.locator(selector).first()
  await expect(el).toBeVisible({ timeout: 10000 })
  /* centred, not merely "in view": a control level with the bottom edge is reachable by the letter
     of scrollIntoViewIfNeeded and awkward for a finger, and the pane is still settling under it */
  await el.evaluate(e => e.scrollIntoView({ block: 'center' }))
  await page.waitForTimeout(400)
  return (await el.boundingBox())!
}

/* Every test here holds a gesture for half a second, waits out the pane's rise and its fall, and
   several of them do that three or four times over. Six running at once on a working machine is
   genuinely slower than Playwright's 30s default, and a timeout there says nothing about the panel. */
test.describe.configure({ timeout: 60_000 })

async function finger(page: Page) {
  const cdp = await page.context().newCDPSession(page)
  return {
    async down(x: number, y: number) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] }) },
    async to(x: number, y: number) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y }] }); await page.waitForTimeout(40) },
    async up() { await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await page.waitForTimeout(400) },
    detach: () => cdp.detach(),
  }
}

/** Hold a tile with a finger until ITS pane opens, then start watching what the house is told.
    `instrument` is the rig the tile should have produced: a room scrolls sideways, and a press
    measured a moment too early lands on the neighbour, which opens a perfectly good pane of the
    wrong kind. Rather than assert on a race, press again. */
async function open(page: Page, room: string, selector: string, instrument: string) {
  const posts: string[] = []
  page.on('request', r => { if (r.method() === 'POST') posts.push(`${new URL(r.url()).pathname} ${r.postData() ?? ''}`.trim()) })
  await page.goto(`/?room=${room}&at=19:40`, { waitUntil: 'networkidle' })
  for (let go = 0; go < 3; go++) {
    const tile = page.locator(selector).first()
    await expect(tile).toBeVisible()
    await tile.scrollIntoViewIfNeeded()      // a finger cannot press what is off the side of a room
    await page.waitForTimeout(700)
    const box = (await tile.boundingBox())!
    const hand = await finger(page)
    await hand.down(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
    await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10000 })
    await hand.up()
    await hand.detach()
    await page.waitForTimeout(700)
    if (await page.locator(instrument).count()) break
    /* Escape rather than the close button: the pane is mid-fall by now and a click on a moving
       target is its own race. */
    await page.keyboard.press('Escape')
    await expect(page.locator('.opened-panel')).toHaveCount(0, { timeout: 5000 })
    await page.waitForTimeout(400)
  }
  await expect(page.locator(instrument)).toHaveCount(1)
  posts.length = 0
  return posts
}

test.describe('with a finger', () => {
  test('the thermostat ring turns under a finger, not just its two buttons', async ({ page }) => {
    const posts = await open(page, 'living', '.tile.climate', '.rig-climate')
    const dial = await boxOf(page, '.rig-dial')
    const cx = dial.x + dial.width / 2, cy = dial.y + dial.height / 2
    const at = (deg: number) => [cx + Math.cos(deg * Math.PI / 180) * dial.width * 0.4,
                                 cy + Math.sin(deg * Math.PI / 180) * dial.height * 0.4] as const

    const before = await page.locator('.rig-dial-n').innerText()
    const hand = await finger(page)
    await hand.down(...at(250))
    for (const deg of [280, 310, 340, 0]) await hand.to(...at(deg))
    /* the number follows the finger while it is down, and the house has not been told yet */
    const during = await page.locator('.rig-dial-n').innerText()
    expect(during, 'the ring did not move under the finger').not.toBe(before)
    expect(posts, 'the house was told before the finger let go').toEqual([])
    await hand.up()
    await hand.detach()

    expect(posts).toHaveLength(1)
    expect(posts[0]).toMatch(/^\/devices\/t1\/set \{"temperature":\d+\}$/)
    const asked = JSON.parse(posts[0].split(' ')[1]).temperature
    expect(asked, 'three o\'clock on the ring is near the warm end').toBeGreaterThan(78)
  })

  test('a lamp dims under a finger', async ({ page }) => {
    const posts = await open(page, 'living', '.tile.light.dimmable', '.rig-light')
    /* A column on a wall, a bar on a phone -- and an iPad in portrait is a phone by this panel's
       860px rule. Drag along whichever way it is lying. */
    const col = await boxOf(page, '.rig-col:not(.warmth)')
    const wide = col.width > col.height
    const at = (f: number) => wide
      ? [col.x + col.width * f, col.y + col.height / 2] as const
      : [col.x + col.width / 2, col.y + col.height * (1 - f)] as const
    const hand = await finger(page)
    await hand.down(...at(0.2))
    await hand.to(...at(0.5))
    await hand.to(...at(0.85))
    await hand.up()
    await hand.detach()
    expect(posts).toHaveLength(1)
    expect(JSON.parse(posts[0].split(' ')[1]).brightness_pct).toBeGreaterThan(60)
  })

  test('a blind is dragged with a finger, and the front door still is not', async ({ page }) => {
    let posts = await open(page, 'living', '.tile.plain.cover', '.rig-cover')
    const win = await boxOf(page, '.rig-window')
    let hand = await finger(page)
    await hand.down(win.x + win.width / 2, win.y + win.height * 0.3)
    await hand.to(win.x + win.width / 2, win.y + win.height * 0.6)
    await hand.to(win.x + win.width / 2, win.y + win.height * 0.75)
    await hand.up()
    await hand.detach()
    expect(posts[0]).toMatch(/^\/devices\/c1\/set \{"position":\d+\}$/)

    posts = await open(page, 'front', '.tile.plain.lock', '.rig-lock')
    const track = await boxOf(page, '.rig-track')
    hand = await finger(page)
    await hand.down(track.x + 44, track.y + track.height / 2)
    await hand.to(track.x + track.width * 0.5, track.y + track.height / 2)
    await hand.up()
    expect(posts, 'half a slide with a finger unlocked the front door').toEqual([])

    await hand.down(track.x + 44, track.y + track.height / 2)
    for (const f of [0.4, 0.7, 0.98]) await hand.to(track.x + track.width * f, track.y + track.height / 2)
    await hand.up()
    await hand.detach()
    expect(posts).toEqual(['/devices/f1/unlock'])
  })

  test('the volume takes a finger', async ({ page }) => {
    const posts = await open(page, 'living', '.tile.media.wide', '.rig-media')
    const bar = await boxOf(page, '.rig-slider')
    const hand = await finger(page)
    await hand.down(bar.x + bar.width * 0.35, bar.y + bar.height / 2)
    await hand.to(bar.x + bar.width * 0.7, bar.y + bar.height / 2)
    await hand.up()
    await hand.detach()
    expect(posts[0]).toMatch(/^\/devices\/m1\/volume /)
  })

  test('a named speed is one tap with a finger', async ({ page }) => {
    const posts = await open(page, 'bedroom', '.tile.plain.fan', '.rig-simple')
    const high = await boxOf(page, '.rig-speed:nth-of-type(3)')
    const tap = await finger(page)
    await tap.down(high.x + high.width / 2, high.y + high.height / 2)
    await tap.up()
    await tap.detach()
    expect(posts).toEqual(['/devices/b3/set {"percentage":100}'])
  })
})
