/* The instrument in an opened device: what each kind is given to work with, and what the house is
   actually told when a hand uses it.
 *
 * These assert on the REQUEST, not on a screenshot, because the failure they exist to catch is a
 * silent one: the pane used to offer a lock, a blind, a camera and a mower a power button that sent
 * act(id, 'on'), an action the brain has no service for, so the house answered 400 and the panel
 * threw an error across the screen. A picture of that pane looks fine.
 */
import { expect, test, type Page } from '@playwright/test'

/* Every test here holds a gesture for half a second, waits out the pane's rise and its fall, and
   several of them do that three or four times over. Six running at once on a working machine is
   genuinely slower than Playwright's 30s default, and a timeout there says nothing about the panel. */
test.describe.configure({ timeout: 60_000 })

/** Hold a tile until ITS pane opens, then start listening to what the panel asks the house for.
    `instrument` is the rig that tile should have produced; a press measured a moment too early
    lands on the neighbour and opens a perfectly good pane of the wrong kind, so press again. */
async function open(page: Page, room: string, selector: string, instrument: string) {
  const posts: string[] = []
  page.on('request', r => { if (r.method() === 'POST') posts.push(`${new URL(r.url()).pathname} ${r.postData() ?? ''}`.trim()) })
  await page.goto(`/?room=${room}&at=19:40`, { waitUntil: 'networkidle' })
  for (let go = 0; go < 3; go++) {
    const tile = page.locator(selector).first()
    await expect(tile).toBeVisible()
    await page.waitForTimeout(600)
    const box = (await tile.boundingBox())!
    await page.mouse.move(box.x + box.width / 2, box.y + Math.min(24, box.height / 2))
    await page.mouse.down()
    /* Wait for the pane rather than for a stopwatch: the hold fires at 420ms, but a loaded machine
       running six of these at once can take a good deal longer to paint it, and a fixed sleep then
       lets go before the press has landed. */
    await expect(page.locator('.pane-rig')).toHaveCount(1, { timeout: 10000 })
    await page.mouse.up()
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

/** Drag inside an element from its middle to a fraction of its box, the way a finger does. */
async function drag(page: Page, selector: string, fx: number, fy: number) {
  const box = (await page.locator(selector).first().boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy, { steps: 8 })
  await page.mouse.up()
  await page.waitForTimeout(400)
}

test('a lamp is dimmed by dragging its column, and the house hears once', async ({ page }) => {
  const posts = await open(page, 'living', '.tile.light.dimmable', '.rig-light')
  await drag(page, '.rig-col:not(.warmth)', 0.5, 0.15)
  /* One call for a whole drag: forty pointermoves into a Zigbee lamp is how a bulb leaves a mesh. */
  expect(posts).toHaveLength(1)
  expect(posts[0]).toMatch(/^\/devices\/l1\/on \{"brightness_pct":\d+\}$/)
  expect(Number(JSON.parse(posts[0].split(' ')[1]).brightness_pct)).toBeGreaterThan(60)
})

test('the three levels a lamp is used at are one tap each', async ({ page }) => {
  const posts = await open(page, 'living', '.tile.light.dimmable', '.rig-light')
  await page.locator('.pane-rig').getByText('Night', { exact: true }).click()
  await page.waitForTimeout(400)
  expect(posts).toEqual(['/devices/l1/on {"brightness_pct":5,"color_temp_kelvin":2200}'])
})

test('a blind is dragged to a position, and can be stopped on the way', async ({ page }) => {
  const posts = await open(page, 'living', '.tile.plain.cover', '.rig-cover')
  await drag(page, '.rig-window', 0.5, 0.7)
  expect(posts[0]).toMatch(/^\/devices\/c1\/set \{"position":\d+\}$/)
  posts.length = 0
  await page.locator('.pane-rig').getByText('Stop there', { exact: true }).click()
  await page.waitForTimeout(300)
  expect(posts).toEqual(['/devices/c1/stop'])
})

test('a door does not open on a tap, or on half a slide', async ({ page }) => {
  const posts = await open(page, 'front', '.tile.plain.lock', '.rig-lock')
  await page.locator('.rig-track').click()
  await page.waitForTimeout(300)
  expect(posts, 'a brush of a sleeve unlocked the front door').toEqual([])

  await drag(page, '.rig-track', 0.5, 0.5)
  expect(posts, 'half a slide unlocked the front door').toEqual([])

  const track = (await page.locator('.rig-track').boundingBox())!
  await page.mouse.move(track.x + 44, track.y + track.height / 2)
  await page.mouse.down()
  await page.mouse.move(track.x + track.width - 6, track.y + track.height / 2, { steps: 12 })
  await page.mouse.up()
  await page.waitForTimeout(400)
  expect(posts).toEqual(['/devices/f1/unlock'])
})

test('no kind is given a control the brain would refuse', async ({ page }) => {
  /* The four with no ('cap','on') in the brain's service table. Their panes must not draw a power
     button at all -- the old one did, for every kind alike. */
  for (const [room, selector, rig] of [['front', '.tile.plain.lock', '.rig-lock'], ['living', '.tile.plain.cover', '.rig-cover'],
                                       ['backyard', '.tile.camera', '.rig-camera'], ['backyard', '.tile.plain.vacuum', '.rig-simple']] as const) {
    await open(page, room, selector, rig)
    const labels = await page.locator('.opened-acts .ctl').evaluateAll(els => els.map(e => e.getAttribute('aria-label')))
    expect(labels.join(), `${selector} still offers a power button`).not.toMatch(/turn it (on|off)/i)
  }
})

test('the thermostat ring is turned by dragging it, and says so while it turns', async ({ page }) => {
  /* The ring shipped as a drawing: every button beside it worked and the ring itself did nothing,
     which is invisible in a screenshot and the first thing a hand finds. */
  const posts = await open(page, 'living', '.tile.climate', '.rig-climate')
  const dial = (await page.locator('.rig-dial').boundingBox())!
  const at = (deg: number) => [dial.x + dial.width / 2 + Math.cos(deg * Math.PI / 180) * dial.width * 0.4,
                               dial.y + dial.height / 2 + Math.sin(deg * Math.PI / 180) * dial.height * 0.4] as const

  const before = await page.locator('.rig-dial-n').innerText()
  await page.mouse.move(...at(250))
  await page.mouse.down()
  for (const deg of [280, 310, 340, 0]) await page.mouse.move(...at(deg), { steps: 3 })
  expect(await page.locator('.rig-dial-n').innerText(), 'the number did not follow the drag').not.toBe(before)
  expect(posts, 'the house was told mid-drag').toEqual([])
  await page.mouse.up()
  await page.waitForTimeout(400)

  expect(posts).toHaveLength(1)
  expect(Number(JSON.parse(posts[0].split(' ')[1]).temperature)).toBeGreaterThan(78)
})

test('a thermostat can be set, told what to do, and pointed at another room\'s sensor', async ({ page }) => {
  const posts = await open(page, 'living', '.tile.climate', '.rig-climate')
  await page.locator('.rig-dial-btn.high').click()
  await page.waitForTimeout(300)
  expect(posts[0]).toMatch(/^\/devices\/t1\/set \{"temperature":\d+\}$/)
  posts.length = 0

  await page.locator('.pane-rig').getByText('Warm it', { exact: true }).click()
  await page.waitForTimeout(300)
  expect(posts).toEqual(['/devices/t1/mode {"hvac_mode":"heat"}'])
  posts.length = 0

  await page.locator('.pane-rig').getByText('Living room', { exact: true }).first().click()
  await page.waitForTimeout(300)
  expect(posts).toEqual(['/devices/t1/sense {"sensor":"te1"}'])
})

test('a fan has named speeds, a plug has a timer, a mower has out and back', async ({ page }) => {
  let posts = await open(page, 'bedroom', '.tile.plain.fan', '.rig-simple')
  await page.locator('.pane-rig').getByText('High', { exact: true }).click()
  await page.waitForTimeout(300)
  expect(posts).toEqual(['/devices/b3/set {"percentage":100}'])

  posts = await open(page, 'kitchen', '.tile.plain.switch', '.rig-simple')
  await page.locator('.pane-rig').getByText('for 30 min', { exact: true }).click()
  await page.waitForTimeout(400)
  expect(posts).toEqual(['/devices/k3/timer {"minutes":30}'])

  posts = await open(page, 'backyard', '.tile.plain.vacuum', '.rig-simple')
  await page.locator('.pane-rig').getByText('Send it out', { exact: true }).click()
  await page.waitForTimeout(300)
  await page.locator('.pane-rig').getByText('Back to the dock', { exact: true }).click()
  await page.waitForTimeout(300)
  expect(posts).toEqual(['/devices/y2/start', '/devices/y2/return'])
})

test('the kinds that only watch can be opened at all, and show their day', async ({ page }) => {
  /* They have no tile -- the room shows them as readings -- so the reading is what opens them. This
     is the only way in, and before it there was none. */
  await page.goto('/?room=living&at=19:40', { waitUntil: 'networkidle' })
  const reading = page.locator('button.reading').first()
  await expect(reading).toBeVisible()
  const box = (await reading.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.waitForTimeout(520)
  await page.mouse.up()

  await expect(page.locator('.opened-panel')).toHaveCount(1)
  await page.waitForTimeout(600)
  await expect(page.locator('.rig-sense')).toHaveCount(1)
  await expect(page.locator('.rig-blip').first()).toBeVisible()
  await expect(page.locator('.opened-acts .ctl')).toHaveCount(2)      // why and rename: a sensor has no verb
})

test('every pane says what this one thing did today', async ({ page }) => {
  await open(page, 'living', '.tile.light.dimmable', '.rig-light')
  const day = page.locator('.pane-day')
  await expect(day).toHaveCount(1)
  const moments = await day.locator('.pane-moment').count()
  expect(moments).toBeGreaterThan(1)
  /* and it is this device's day, not the house's: the log is asked by subject */
  await expect(day).not.toContainText('Locked')
})
