/* The face, in the browser that is actually served the panel.

   This file exists because of one specific way a face can be entirely correct in the source and
   absent from the screen. panel.css used to declare `-webkit-backdrop-filter` by hand alongside the
   standard property; the CSS minifier read that pair as "the prefixed one covers every target" and
   emitted only the prefixed one. Chrome 153 removed the -webkit- alias, so every frosted surface in
   the BUILT panel -- the cards, the rail, both panes, the whole of glass -- went flat, while the
   source still plainly said blur and every unit test still passed. Nothing that reads the stylesheet
   can catch that. Only the built panel in a real browser can, which is what this is. */
import { expect, test, type Page } from '@playwright/test'

/* the standard property and the old alias, because which one survives the build is exactly the
   thing in question -- a surface is frosted if the browser ended up with either */
async function frost(page: Page, sel: string) {
  return page.evaluate((s) => {
    const el = document.querySelector(s)
    if (!el) return 'no such element'
    const cs = getComputedStyle(el)
    const std = cs.getPropertyValue('backdrop-filter')
    const wk = cs.getPropertyValue('-webkit-backdrop-filter')
    return [std, wk].find((v) => v && v !== 'none') ?? 'none'
  }, sel)
}

/* a room card on home, and a lamp inside a room: the two surfaces a person actually looks at.
   Not any `.tile` -- a camera turns its own frost off on purpose, because it brings a picture and
   is never overpainted. */
test('a card is frosted in the panel the browser is actually given', async ({ page }) => {
  // layout=stack pinned: a room card only exists on that home, and a spec that reads the house's
  // own setting is a spec that passes or fails on how someone left the mock
  await page.goto('/?layout=stack&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.room-card').first()).toBeVisible()
  expect(await frost(page, '.room-card')).toContain('blur')
})

test('glass keeps its blur once the house is set to it', async ({ page }) => {
  await page.goto('/?face=glass&room=living&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.light').first()).toBeVisible()
  expect(await page.getAttribute('.shell', 'data-face')).toBe('glass')
  expect(await frost(page, '.tile.light')).toContain('blur')
})

test('a pane is frosted too, which is what makes it a pane', async ({ page }) => {
  await page.goto('/?face=glass&sheet=house&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.house-panel')).toBeVisible()
  expect(await frost(page, '.house-panel')).toContain('blur')
})

/* A face decides what the panel is made of. It does not get to move a control, and this is what
   that turns into when it does: `[data-face='glass'] .back` declared `position: relative`, which
   beats a plain `.opened-close`, so the pane's close button fell back into the flow and landed
   thirty pixels off the left edge of the screen -- present, focusable, and unreachable by a finger.
   A panel on a wall has no keyboard, so Escape was not a way out. */
test('the way out of a pane is in the same place whatever the panel is made of', async ({ page }) => {
  const where: Record<string, { x: number; y: number }> = {}
  for (const face of ['paper', 'glass']) {
    await page.goto(`/?face=${face}&room=living&at=19:40`, { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.light').first()).toBeVisible()
    await page.waitForTimeout(400)

    const tile = page.locator('.tile.light').first()
    const b = (await tile.boundingBox())!
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2)
    await page.mouse.down()
    await page.waitForTimeout(470)
    await page.mouse.up()
    await expect(page.locator('.opened-panel')).toBeVisible()
    await page.waitForTimeout(600)

    const close = (await page.locator('.opened-close').boundingBox())!
    const pane = (await page.locator('.opened-panel').boundingBox())!
    expect(close.x, `${face}: the close button is off the left of the screen`).toBeGreaterThan(0)
    expect(close.x + close.width, `${face}: the close button is off the right of the screen`)
      .toBeLessThanOrEqual(1280)
    expect(close.x, `${face}: the close button is not inside the pane`).toBeGreaterThan(pane.x)
    where[face] = { x: Math.round(close.x), y: Math.round(close.y) }

    await page.locator('.opened-close').click()
    await expect(page.locator('.opened-panel')).toHaveCount(0)
  }
  expect(where.glass).toEqual(where.paper)
})

/* What a pane does to the room behind it. Paper pushes it back and blurs it; glass cannot, for two
   reasons that both show up on the screen. A pane over an already-blurred room is a dark sheet over
   mush -- the blur the pane is MADE of has nothing left to work on. And a pane is only a drawer if
   the row you came from is still legible above it. So under glass the room stays put and a scrim
   takes it down. */
test('a pane dims the room under glass and blurs it under paper', async ({ page }) => {
  const room = () => page.evaluate(() => {
    const st = getComputedStyle(document.querySelector('.stage')!)
    const veil = document.querySelector('.opened-veil')
    return {
      filter: st.filter,
      transform: st.transform,
      scrim: veil ? getComputedStyle(veil).backgroundColor : 'no veil',
    }
  })

  for (const face of ['paper', 'glass']) {
    await page.goto(`/?face=${face}&room=living&at=19:40`, { waitUntil: 'networkidle' })
    await expect(page.locator('.tile.light').first()).toBeVisible()
    await page.waitForTimeout(400)

    const tile = page.locator('.tile.light').first()
    const b = (await tile.boundingBox())!
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2)
    await page.mouse.down()
    await page.waitForTimeout(470)
    await page.mouse.up()
    await expect(page.locator('.opened-panel')).toBeVisible()
    await page.waitForTimeout(700)

    const r = await room()
    if (face === 'paper') {
      expect(r.filter, 'paper stopped blurring the room it pushed back').toContain('blur')
    } else {
      expect(r.filter, 'glass blurred the room, leaving its own pane nothing to blur').not.toContain('blur')
      expect(r.transform, 'glass moved the room it was meant to leave where it was')
        .toMatch(/^(none|matrix\(1, 0, 0, 1, 0, 0\))$/)
      // a scrim with something in it, and not so much of it that the room is gone
      const a = Number(r.scrim.match(/[\d.]+(?=\))/)?.[0] ?? (r.scrim === 'rgba(0, 0, 0, 0)' ? 0 : 1))
      expect(a, `glass left the room undimmed: ${r.scrim}`).toBeGreaterThan(0.3)
      expect(a, `glass dimmed the room out of existence: ${r.scrim}`).toBeLessThan(0.75)
    }
  }
})

/* The order of the pane move, which is the part that breaks silently. The numbers themselves are
   frame-noisy on a loaded machine -- panel.css carries the measured ones and why they land where
   they do -- but the sequence is not: the bottom bar gets out of the way BEFORE the pane rises, the
   object inside is still settling after the pane has landed, and on the way out the bar does not
   come back until the pane has gone. Read off the transitions' own clocks, because a screenshot
   cannot see an order and a sampled frame is coarser than the gaps being asserted. */
test('under glass the house gets out of the way first, and the object lands last', async ({ page }) => {
  await page.goto('/?face=glass&room=living&at=19:40&nav=top', { waitUntil: 'networkidle' })
  await expect(page.locator('.tile.light').first()).toBeVisible()
  await page.waitForTimeout(400)

  await page.evaluate(() => {
    const w = window as any
    w.__log = []
    const name = (el: Element) =>
      el.classList.contains('opened-panel') ? 'pane'
        : el.classList.contains('bottombar') ? 'bar'
          : el.classList.contains('opened-hero') ? 'object' : ''
    for (const ev of ['transitionstart', 'transitionend'])
      document.addEventListener(ev, (e) => {
        const n = e.target instanceof Element ? name(e.target) : ''
        if (n && (e as TransitionEvent).propertyName === 'transform')
          w.__log.push({ at: performance.now(), what: `${n}:${ev === 'transitionstart' ? 'start' : 'end'}` })
      }, true)
  })

  const tile = page.locator('.tile.light').first()
  const b = (await tile.boundingBox())!
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2)
  await page.mouse.down()
  await page.waitForTimeout(470)
  await page.mouse.up()
  await expect(page.locator('.opened-panel')).toBeVisible()
  await page.waitForTimeout(1400)
  await page.locator('.opened-close').click()
  await page.waitForTimeout(1400)

  const log: { at: number; what: string }[] = await page.evaluate(() => (window as any).__log)
  const when = (what: string, nth = 0) => log.filter((e) => e.what === what)[nth]?.at
  const seen = log.map((e) => e.what)

  expect(seen, `nothing moved: ${JSON.stringify(seen)}`).toContain('pane:start')
  expect(when('bar:start'), 'the bar did not leave before the pane rose')
    .toBeLessThan(when('pane:start'))
  expect(when('object:end'), 'the object stopped before the pane landed, so it is printed on it')
    .toBeGreaterThan(when('pane:end'))
  // the second of each is the way out
  expect(when('bar:start', 1), 'the bar came back before the pane had gone')
    .toBeGreaterThan(when('pane:start', 1) + 300)
})

/* What the face does when it is asked not to move. All eight moves collapse to opacity: nothing
   travels, nothing scales, nothing blurs, and the field stops drifting. Two things are worth
   holding, and they pull in opposite directions -- that nothing is left moving, and that the row
   still ARRIVES rather than appearing between two frames. */
test.describe('asked not to move', () => {
  test.use({ reducedMotion: 'reduce' })

  test('leaves nothing running under glass, on the screen or in the sky', async ({ page }) => {
    await page.goto('/?face=glass&layout=rail&nav=top&at=19:40', { waitUntil: 'networkidle' })
    await expect(page.locator('.bento-card').first()).toBeVisible()
    await page.waitForTimeout(900)

    const still = await page.evaluate(() => {
      const moving: string[] = []
      for (const el of document.querySelectorAll('*')) {
        const cs = getComputedStyle(el)
        const where = (el.className || el.tagName).toString().slice(0, 40)
        if (cs.animationName !== 'none') moving.push(`${where}: animation ${cs.animationName}`)
        /* The orb's blooms are the one filter in the face that is not a move. They are PAINTED
           through a blur, the way a gradient is painted, and what has been taken away under
           reduced motion is the turn -- which was the whole of the vestibular part. A filter only
           moves something if something is happening to it, and the check above is what says
           nothing is. Everything else in the face is still held to none. */
        if (cs.filter !== 'none' && !el.closest('.say-orb')) moving.push(`${where}: filter ${cs.filter}`)
        if (cs.transitionDuration.split(',').some((d) => parseFloat(d) > 0 && !/opacity/.test(cs.transitionProperty)))
          moving.push(`${where}: transition ${cs.transitionProperty}`)
      }
      return [...new Set(moving)]
    })
    expect(still, `still moving: ${still.join(' | ')}`).toEqual([])
  })

  test('still lets the row arrive, as the fade every move collapses to', async ({ page }) => {
    const seen: { o: string; translate: string | null }[] = []
    await page.exposeFunction('__push', (r: { o: string; translate: string | null }) => { seen.push(r) })
    await page.addInitScript(() => {
      const tick = () => {
        const row = document.querySelector('.bento')
        if (row) {
          const card = row.querySelector('.bento-card')
          ;(window as any).__push({
            o: Number(getComputedStyle(row).opacity).toFixed(2),
            translate: card ? getComputedStyle(card).translate : null,
          })
        }
        requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    })
    await page.goto('/?face=glass&layout=rail&nav=top&at=19:40', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1400)

    // it arrived rather than simply being there
    expect(seen.some((r) => r.o === '0.00'), 'the row never faded in; it was just suddenly there').toBe(true)
    expect(seen[seen.length - 1].o, 'the row never finished arriving').toBe('1.00')
    // and nothing travelled on the way. A card held 696px right for even one painted frame is the
    // move this was meant to remove, whether or not a transition was carrying it there.
    const travelled = seen.filter((r) => r.translate && r.translate !== 'none' && !/^0px( 0px)?$/.test(r.translate))
    expect(travelled.length, `a card travelled: ${travelled[0]?.translate}`).toBe(0)
  })
})

/* The floor. A host that cannot paint a backdrop-filter gets glass flattened rather than taken
   away, and ?flat=1 is the only way to see that on a machine that can. The point is that the face
   survives: the rim, the sweep and the shadow are all still drawn, and the cards stop being
   translucent -- which they must, because an unblurred glass card is .34 alpha over the open sky
   and hardly a card at all. */
test('glass on the floor keeps its drawing and loses only its depth', async ({ page }) => {
  const look = () => page.evaluate(() => {
    const of = (sel: string) => {
      const el = document.querySelector(sel)
      if (!el) return null
      const cs = getComputedStyle(el)
      return {
        frost: [cs.getPropertyValue('backdrop-filter'), cs.getPropertyValue('-webkit-backdrop-filter')]
          .find((v) => v && v !== 'none') ?? 'none',
        fill: cs.backgroundImage,
        rim: getComputedStyle(el, '::after').backgroundImage,
        shadow: cs.boxShadow,
      }
    }
    return { card: of('.bento-card .tile.plain, .tile.plain, .room-card'), rail: of('.rail') }
  })

  // nav=side, because the side rail is furniture rather than a card and takes the floor differently
  await page.goto('/?face=glass&layout=rail&nav=side&at=19:40', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento-card').first()).toBeVisible()
  await page.waitForTimeout(700)
  const lens = await look()
  expect(lens.card!.frost, 'glass was not blurring in the first place').toContain('blur')

  await page.goto('/?face=glass&layout=rail&nav=side&at=19:40&flat=1', { waitUntil: 'networkidle' })
  await expect(page.locator('.bento-card').first()).toBeVisible()
  await page.waitForTimeout(700)
  const floor = await look()

  expect(await page.getAttribute('.shell', 'data-flat'), 'the floor never came on').toBe('')
  expect(floor.card!.frost, 'the floor is still asking for a blur it cannot paint').toBe('none')
  expect(floor.rail!.frost, 'the rail is still asking for a blur it cannot paint').toBe('none')
  // the drawing survives: the same rim, and a shadow still under it
  expect(floor.card!.rim, 'the rim went with the blur').toBe(lens.card!.rim)
  expect(floor.card!.shadow, 'the shadow went with the blur').toBe(lens.card!.shadow)
  // and the fill stopped being see-through
  expect(lens.card!.fill, 'the lens fill was already opaque, so this proves nothing').toMatch(/\//)
  expect(floor.card!.fill, `the floor left a translucent card: ${floor.card!.fill}`)
    .not.toMatch(/oklch\([^)]*\//)
})
