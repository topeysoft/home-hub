// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What a thermostat is doing, in the browser that is actually served the panel.

   The unit tests next door pin the decision -- the action picks the color, idle picks none -- and
   the arithmetic that turns it into a card. Neither can see whether the class the tile writes
   reaches a rule that paints anything, because panel.css is one flat global sheet and the answer
   depends on what else in it happens to match.

   That is not hypothetical here. Scoping the icon badge to the two action classes let an idle
   thermostat fall through to `.tile.on .tile-icon`, five thousand lines up, which paints every lit
   tile's badge in --lamp. A holding thermostat wore the "a light is on" accent as the loudest mark
   on an otherwise quiet card. Every unit test passed, the class was correct, both screens rendered.
   Only the built panel in a real browser shows it. */
import { expect, test, type Page } from '@playwright/test'

/* The mock's thermostat is cooling, so the other two states have to be asked for. Rewriting the
   brain's answer rather than adding mock devices keeps ONE thermostat across all three shots --
   same room, same mode, same target -- so anything that differs is the action and nothing else. */
async function acting(page: Page, action: string) {
  await page.route('**/home*', async (route) => {
    const res = await route.fetch()
    const body = (await res.text()).replace(/"hvac_action":\s*"cooling"/g, `"hvac_action":"${action}"`)
    await route.fulfill({ response: res, body })
  })
  await page.goto('/?layout=wall&nav=top&at=20:10&wx=cloudy', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.climate')).toBeVisible()
}

const card = (page: Page) =>
  page.evaluate(() => {
    const t = document.querySelector('.tile.climate')!
    const cs = getComputedStyle(t)
    const icon = document.querySelector('.tile.climate .tile-icon')!
    return {
      cls: t.className,
      bg: cs.backgroundImage,
      icon: getComputedStyle(icon).backgroundColor,
      says: (t.getAttribute('aria-label') ?? '').toLowerCase(),
    }
  })

test('a running thermostat paints its card, and says which way', async ({ page }) => {
  await acting(page, 'cooling')
  const cool = await card(page)
  expect(cool.cls).toContain('act-cooling')
  expect(cool.bg).toContain('oklch')            // a painted card, not the surface
  expect(cool.says).toContain('cooling')

  await acting(page, 'heating')
  const heat = await card(page)
  expect(heat.cls).toContain('act-heating')
  expect(heat.bg).toContain('oklch')
  expect(heat.says).toContain('heating')

  // the two are not the same picture: the hues are 250 and 55, and a build that
  // collapsed them would still satisfy everything above
  expect(heat.bg).not.toBe(cool.bg)
})

/* The case the whole change exists for, and the one a thermostat is in most of the day. It says so as a
   person would, "Nothing to do", not the device's "idle" (docs/wording.md, design/words-rooms/). */
test('a thermostat with nothing to do wears nothing at all', async ({ page }) => {
  await acting(page, 'idle')
  const idle = await card(page)
  expect(idle.says).toContain('nothing to do')
  expect(idle.cls).not.toContain('act-')
  expect(idle.bg).not.toContain('oklch')        // the ordinary card, not a painted one

  /* and NOT the lamp accent. --lamp is #e9b872; a badge anywhere near it here means the tile fell
     through to `.tile.on .tile-icon` again. Read as numbers rather than as a string, because the
     exact notation a browser returns is not the thing being asserted. */
  const [r, g, b] = idle.icon.match(/\d+/g)!.slice(0, 3).map(Number)
  const lamp = Math.hypot(r - 233, g - 184, b - 114)
  expect(lamp).toBeGreaterThan(60)
})

/* Reported 9 October, a phone in dark mode by day: on a cooling card pale enough to flip its ink dark,
   the chosen chips -- "Cool", "Thermostat" -- were dark text on a dark chip, and the card's name stayed
   light. Both halves of a chosen chip and the name come off the card's one ink, at noon and at night. */
const lum = (rgb: string) => { const [r, g, b] = rgb.match(/[\d.]+/g)!.map(Number); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 }
for (const at of ['13:00', '21:00']) {
  test(`a painted card's chosen chips and name read, on a phone at ${at}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/?room=living&at=${at}&shade=dark`, { waitUntil: 'networkidle' })
    const tile = page.locator('.tile.climate.act-cooling').first()
    await expect(tile).toBeVisible()
    const seen = await tile.evaluate(t => {
      const chip = t.querySelector('.clim-chip.on')!, cs = getComputedStyle(chip)
      return { text: cs.color, fill: cs.backgroundColor, name: getComputedStyle(t.querySelector('.tile-name')!).color, reading: getComputedStyle(t.querySelector('.clim-big')!).color }
    })
    expect(Math.abs(lum(seen.text) - lum(seen.fill)), `"${seen.text}" on "${seen.fill}"`).toBeGreaterThan(0.5)
    expect(seen.name, 'the name is the card\'s ink, like its reading').toBe(seen.reading)
  })
}
