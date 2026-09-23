// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Hold a button and the end of the strip walks.
 *
 * A tap has to move exactly one light, because the whole point of this control is that somebody is
 * three lights out and wants to be none. But a household that is thirty out must not tap thirty
 * times, so holding accelerates -- slowly at first, so the single light is still reachable by
 * holding a moment too long, then faster.
 *
 * It is here rather than in the pane because it is the shape of the gesture and not the drawing of
 * it: the numbers below are what makes this feel like moving an end rather than operating a
 * repeater, and a number that decides how something feels is worth a test. design/strip/Nudge.dc.html.
 */

/** A tap, and the first step of a hold: always exactly one light. */
export const FIRST = 1
/** How long a hold waits before it starts walking. Longer than a tap, shorter than a doubt. */
export const BEFORE = 420
/** The gap between steps at the start of a walk, and the floor it accelerates to. */
export const SLOWEST = 110
export const FASTEST = 28
/** How many steps it takes to get there. Eight is about a second of holding. */
export const RAMP = 8

/** The pause before step `n` of a hold (n = 0 is the first step after BEFORE). */
export function gap(n: number): number {
  const t = Math.min(1, Math.max(0, n) / RAMP)
  return Math.round(SLOWEST + (FASTEST - SLOWEST) * t)
}

/** How many lights step `n` moves. One at a time until the gap is at its floor, then in threes --
 *  below about thirty milliseconds a step, moving one light at a time stops looking like motion and
 *  starts looking like a stuck number. */
export function step(n: number): number {
  return gap(n) > FASTEST ? FIRST : 3
}

/** Everything a hold does, as the list of moves it would make over `ms`. Exported for the test:
 *  the feel of this is the sum of the numbers above and there is no other way to check it. */
export function walk(ms: number): { at: number; by: number }[] {
  const out: { at: number; by: number }[] = []
  let t = BEFORE
  for (let n = 0; t <= ms; n++) {
    out.push({ at: t, by: step(n) })
    t += gap(n)
  }
  return out
}
