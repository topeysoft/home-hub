/* The camera's bottom sheet plays, and what that is allowed to cost.
 *
 * Two properties, and the second is the one with a bill attached. The sheet shows the still at once
 * and then moves -- and while it moves it stops asking the brain for stills, because a JPEG a second
 * from a cloud camera that is already sending video is a call that buys nothing. And nothing is
 * asked of the camera at all until the sheet has been up for SETTLE: the sheet opens on a HOLD, a
 * gesture people make by accident on a wall panel, and an accident must not wake a doorbell.
 *
 * The mock has no video, so the stream is fulfilled here with real JPEG bytes drawn in the page --
 * an <img> will not decode anything less, and `mjpeg()` decides it is playing by watching
 * naturalWidth. WebRTC is tried first and fails on its socket, which is the fallback this exercises.
 */
import { expect, test, type Page } from '@playwright/test'
import { freeze } from './press'

const ROOM = '/?room=backyard&at=13:00'

/** A motion-JPEG body a browser will actually play, drawn in the page it is served to. */
async function mjpegBody(page: Page) {
  const frames = await page.evaluate(() =>
    ['#2f6f4f', '#6f2f3f', '#2f4f6f'].map(colour => {
      const c = document.createElement('canvas')
      c.width = 640; c.height = 360
      const x = c.getContext('2d')!
      x.fillStyle = colour; x.fillRect(0, 0, 640, 360)
      return c.toDataURL('image/jpeg', 0.8).split(',')[1]
    }))
  return Buffer.concat(frames.map(f => Buffer.from(f, 'base64')).flatMap(f => [
    Buffer.from(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${f.length}\r\n\r\n`), f, Buffer.from('\r\n'),
  ]))
}

/** Hold the camera tile until its sheet is up. The press is advanced by hand -- see press.ts. */
async function holdCamera(page: Page) {
  const box = (await page.locator('.tile.camera').first().boundingBox())!
  await freeze(page)
  await page.mouse.move(box.x + box.width / 2, box.y + 24)
  await page.mouse.down()
  await page.clock.runFor(500)        // hold.ts fires at 420
  await page.mouse.up()
  await expect(page.locator('.rig-still')).toHaveCount(1)
}

test('the sheet moves, and stops asking for stills while it does', async ({ page }) => {
  await page.goto(ROOM, { waitUntil: 'networkidle' })
  const body = await mjpegBody(page)
  let stills = 0
  page.on('request', r => { if (/\/image/.test(r.url())) stills++ })
  await page.route('**/devices/*/stream*', r =>
    r.fulfill({ status: 200, headers: { 'Content-Type': 'multipart/x-mixed-replace; boundary=frame' }, body }))

  await holdCamera(page)
  await page.clock.resume()
  await expect(page.locator('.rig-still')).toHaveClass(/playing/, { timeout: 15000 })

  // nothing says Live unless a picture is moving -- and this one is
  await expect(page.locator('.rig-still-tag')).toHaveText(/Live|Recording/)
  expect(await page.locator('.rig-still-moving').evaluate(i => (i as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0)

  const asked = stills
  await page.waitForTimeout(6000)     // longer than the still's own 5s beat on this screen
  expect(stills - asked, 'the brain was asked for stills while the picture was already moving').toBe(0)
})

test('a sheet shut before it settles never wakes the camera', async ({ page }) => {
  await page.goto(ROOM, { waitUntil: 'networkidle' })
  let streams = 0
  page.on('request', r => { if (/\/stream/.test(r.url())) streams++ })
  await page.route('**/devices/*/stream*', r => r.fulfill({ status: 502, body: '' }))

  await holdCamera(page)
  await page.clock.runFor(300)        // shut well inside SETTLE, the way a hold nobody meant is
  await page.keyboard.press('Escape')
  await page.clock.resume()
  await expect(page.locator('.rig-still')).toHaveCount(0)
  await page.waitForTimeout(2500)
  expect(streams, 'a sheet opened by accident asked the camera for a stream').toBe(0)
})
