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

/* The case the whole change exists for, and the one a thermostat is in most of the day. */
test('a thermostat holding at temperature wears nothing at all', async ({ page }) => {
  await acting(page, 'idle')
  const idle = await card(page)
  expect(idle.says).toContain('holding')
  expect(idle.cls).not.toContain('act-')
  expect(idle.bg).not.toContain('oklch')        // the ordinary card, not a painted one

  /* and NOT the lamp accent. --lamp is #e9b872; a badge anywhere near it here means the tile fell
     through to `.tile.on .tile-icon` again. Read as numbers rather than as a string, because the
     exact notation a browser returns is not the thing being asserted. */
  const [r, g, b] = idle.icon.match(/\d+/g)!.slice(0, 3).map(Number)
  const lamp = Math.hypot(r - 233, g - 184, b - 114)
  expect(lamp).toBeGreaterThan(60)
})
