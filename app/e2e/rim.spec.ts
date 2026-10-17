// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Every glass card on Home wears the same rim, the TV card included.

   The rim is each card's ::after, masked to its edge. The media card's own ::after rule outweighed
   it and painted that edge with a dark gradient meant for something else: on the dark look nobody
   could see it, on the light one the TV card had two dark lines down its sides. panel.css is one
   flat sheet, so the only way to know which rule won is to ask the browser that was served it. */
import { expect, test } from '@playwright/test'

for (const shade of ['light', 'dark']) {
  test(`on the ${shade} look every card on Home has the same rim`, async ({ page }) => {
    await page.goto(`/?shade=${shade}&at=22:30`)
    await expect(page.locator('.bento .tile.media').first()).toBeVisible()
    const rims = await page.locator('.bento .tile').evaluateAll((tiles) =>
      tiles.map((t) => ({ media: t.classList.contains('media'), rim: getComputedStyle(t, '::after').backgroundImage })))
    const media = rims.find((r) => r.media), other = rims.find((r) => !r.media)
    expect(media, 'the mock house has a TV card on Home').toBeTruthy()
    expect(media!.rim).toBe(other!.rim)
  })
}
