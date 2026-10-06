// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Holding a card to open it, and the one thing that goes wrong when it works.
 *
 * The bug this holds shut: a hold opens a panel UNDER the finger that is still down, and the click
 * that ends the press is delivered to whatever is beneath the point when the finger LIFTS -- by
 * then the panel, not the card. On an iPad-sized wall panel the light pane's presets land where the
 * finger was, so letting go of a lamp at 35% to open it also set it to 100%. `e2e/gesture.touch`
 * proves that end to end in a real browser; this pins the RULE that makes the cure safe, which is
 * the part a later tidy-up would take out: the swallow belongs to one press, and the next press
 * cancels it. Get that wrong and the cure eats the tap the person opened the panel to make.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { vHold } from '../src/hold'

const HOLD = 420   // hold.ts's own; a press has to outlast it

/** The card, with the directive on it the way Vue's `created` hook would put it. */
function card(open = vi.fn()) {
  const el = document.createElement('div')
  document.body.appendChild(el)
  vHold.created!.call(null as never, el, { value: open } as never, null as never, null as never)
  return { el, open }
}

/** A pointer or mouse event at a point. happy-dom has no PointerEvent; MouseEvent carries
    everything hold.ts reads off one, and the missing pointerId makes setPointerCapture throw,
    which hold.ts already swallows -- the same as a browser that refuses the capture. */
const at = (type: string, x: number, y: number) =>
  new MouseEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true, cancelable: true })

/** Somewhere else entirely -- the panel that just opened over the card. */
function elsewhere() {
  const el = document.createElement('button')
  const tapped = vi.fn()
  el.addEventListener('click', tapped)
  document.body.appendChild(el)
  return { el, tapped }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('press and hold', () => {
  it('opens the card once the press outlasts the hold', () => {
    const { el, open } = card()
    el.dispatchEvent(at('pointerdown', 100, 100))
    expect(open).not.toHaveBeenCalled()
    vi.advanceTimersByTime(HOLD + 20)
    expect(open).toHaveBeenCalledTimes(1)
  })

  it('does not open when the finger leaves before then', () => {
    const { el, open } = card()
    el.dispatchEvent(at('pointerdown', 100, 100))
    vi.advanceTimersByTime(HOLD - 80)
    el.dispatchEvent(at('pointerup', 100, 100))
    vi.advanceTimersByTime(400)
    expect(open).not.toHaveBeenCalled()
  })

  it('does not open when the finger is scrolling', () => {
    const { el, open } = card()
    el.dispatchEvent(at('pointerdown', 100, 100))
    el.dispatchEvent(at('pointermove', 140, 100))   // past SLOP: this is a scroll
    vi.advanceTimersByTime(HOLD + 60)
    expect(open).not.toHaveBeenCalled()
  })

  it('swallows the click the release lands on, even though it lands somewhere else', () => {
    // the whole bug, in four lines: the panel opened under the finger, and the click went to it
    const { el } = card()
    const panel = elsewhere()
    el.dispatchEvent(at('pointerdown', 100, 100))
    vi.advanceTimersByTime(HOLD + 20)
    el.dispatchEvent(at('pointerup', 100, 100))
    panel.el.dispatchEvent(at('click', 100, 100))
    expect(panel.tapped).not.toHaveBeenCalled()
  })

  it('lets the next real tap through, because a new press ends the swallow', () => {
    /* The reason the swallow is scoped to a press rather than to a stopwatch. Somebody holds a lamp
       open in ORDER to touch something in it, and they are quick about it. A window wide enough to
       be sure of catching the stray click is wide enough to eat this one. */
    const { el } = card()
    const panel = elsewhere()
    el.dispatchEvent(at('pointerdown', 100, 100))
    vi.advanceTimersByTime(HOLD + 20)
    el.dispatchEvent(at('pointerup', 100, 100))
    panel.el.dispatchEvent(at('click', 100, 100))          // the stray one, eaten
    expect(panel.tapped).not.toHaveBeenCalled()

    panel.el.dispatchEvent(at('pointerdown', 100, 100))    // a new press: this one is meant
    panel.el.dispatchEvent(at('click', 100, 100))
    expect(panel.tapped).toHaveBeenCalledTimes(1)
  })

  it('a press that never opened anything swallows nothing', () => {
    const { el } = card()
    const panel = elsewhere()
    el.dispatchEvent(at('pointerdown', 100, 100))
    vi.advanceTimersByTime(HOLD - 100)                     // a tap, not a hold
    el.dispatchEvent(at('pointerup', 100, 100))
    panel.el.dispatchEvent(at('click', 100, 100))
    expect(panel.tapped).toHaveBeenCalledTimes(1)
  })

  it('a click somewhere far from the release is somebody else’s', () => {
    /* The swallow is armed at a point, not over the whole screen: a click that turns up across the
       panel did not come from this finger, and eating it would be this bug pointed the other way. */
    const { el } = card()
    const panel = elsewhere()
    el.dispatchEvent(at('pointerdown', 100, 100))
    vi.advanceTimersByTime(HOLD + 20)
    el.dispatchEvent(at('pointerup', 100, 100))
    panel.el.dispatchEvent(at('click', 700, 620))
    expect(panel.tapped).toHaveBeenCalledTimes(1)
  })

  it('is not left armed for good when no click ever comes', () => {
    const { el } = card()
    const panel = elsewhere()
    el.dispatchEvent(at('pointerdown', 100, 100))
    vi.advanceTimersByTime(HOLD + 20)
    el.dispatchEvent(at('pointerup', 100, 100))
    vi.advanceTimersByTime(2000)                           // past the backstop
    panel.el.dispatchEvent(at('click', 100, 100))
    expect(panel.tapped).toHaveBeenCalledTimes(1)
  })
})
