/* Every screen a person will see, opened at a fixed hour against the same house.

   Not a picture test — it asserts the things that are true of a screen whether or not it looks
   right: it drew something, it said nothing about undefined, the browser logged no errors, and the
   page does not scroll sideways on any of the sizes the panel runs at. */
import { expect, test } from '@playwright/test'

const SIZES = { wall: { width: 1920, height: 1080 }, kiosk: { width: 1280, height: 800 },
                tablet: { width: 820, height: 1180 }, phone: { width: 390, height: 844 } } as const

const SCREENS: [name: string, size: keyof typeof SIZES, url: string][] = [
  ['home, evening', 'kiosk', '/?at=19:40'],
  ['home, midday', 'kiosk', '/?at=13:00&wx=sunny'],
  ['home, rain at night', 'kiosk', '/?at=23:10&wx=rainy'],
  ['home, rail', 'kiosk', '/?layout=rail&at=19:40'],
  ['a room', 'kiosk', '/?room=living&at=19:40'],
  ['a room at three columns', 'kiosk', '/?room=living&at=19:40'],
  ['the kitchen', 'kiosk', '/?room=kitchen&at=19:40'],
  ['things not placed yet', 'kiosk', '/?room=unassigned&at=19:40'],
  ['a room with nothing in it', 'kiosk', '/?room=bath&at=19:40'],
  ['resting', 'kiosk', '/?rest=1&at=22:00'],
  ['resting by day', 'kiosk', '/?rest=1&at=15:00'],
  ['the add sheet', 'kiosk', '/?sheet=add&at=19:40'],
  ['the routines sheet', 'kiosk', '/?sheet=routines&at=19:40'],
  ['the why sheet', 'kiosk', '/?sheet=why&room=living&at=19:40'],
  ['the location sheet', 'kiosk', '/?sheet=location&at=19:40'],
  ['the code sheet', 'kiosk', '/?sheet=code&at=19:40'],
  ['the hub sheet', 'kiosk', '/?sheet=hub&at=19:40'],
  ['signing an account in again', 'kiosk', '/?sheet=add&signin=r1&at=19:40'],
  ['setup, welcome', 'kiosk', '/?setup=1&page=welcome&at=13:00'],
  ['setup, rooms', 'kiosk', '/?setup=1&page=rooms&at=13:00'],
  ['setup, devices', 'kiosk', '/?setup=1&page=devices&at=13:00'],
  ['setup, done', 'kiosk', '/?setup=1&page=done&at=13:00'],
  ['the join screen', 'kiosk', '/?join=1&at=13:00'],
  ['home on a wall', 'wall', '/?at=19:40'],
  ['home on a tablet', 'tablet', '/?at=19:40'],
  ['home on a phone', 'phone', '/?at=19:40'],
  ['a room on a phone', 'phone', '/?room=living&at=19:40'],
  ['the add sheet on a phone', 'phone', '/?sheet=add&at=19:40'],
  ['setup on a phone', 'phone', '/?setup=1&page=rooms&at=13:00'],
  ['the join screen on a phone', 'phone', '/?join=1&at=13:00'],
]

/* Noise a panel makes that is not the panel's fault: the mock serves no artwork or camera frames. */
const EXPECTED = [/favicon/i, /\/x\.jpg/, /entity_picture/, /\/image\b/, /\/stream\b/, /ERR_CONNECTION/, /Failed to load resource/]

for (const [name, size, url] of SCREENS) {
  test(name, async ({ page }) => {
    const problems: string[] = []
    page.on('console', m => { if (m.type() === 'error' && !EXPECTED.some(r => r.test(m.text()))) problems.push(m.text()) })
    page.on('pageerror', e => problems.push(String(e)))

    await page.setViewportSize(SIZES[size])
    await page.goto(url, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)          // sheets and the sky settle

    // it drew something
    await expect(page.locator('.shell')).toBeVisible()
    const text = await page.locator('body').innerText()
    expect(text.trim().length, 'the screen is blank').toBeGreaterThan(10)

    // it did not leak a value into the words
    for (const leak of ['undefined', 'NaN', '[object Object]']) {
      expect(text, `"${leak}" is on the screen`).not.toContain(leak)
    }

    // nothing the panel itself is unhappy about
    expect(problems, 'the browser logged errors').toEqual([])

    // and it fits: a wall panel that scrolls sideways has nowhere to scroll to
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, 'the page scrolls sideways').toBeLessThanOrEqual(1)
  })
}
