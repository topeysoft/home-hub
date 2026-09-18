// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * A card reading itself off the Home row.
 *
 * Something that was on has gone off from elsewhere -- a routine, somebody in another room -- and
 * nobody's hand is on the screen, so the card says what it now is for a beat, fades, and the row
 * closes over it. Three steps on two clocks: the beat and the sweep are timeouts, and the fade is
 * armed two animation frames after the beat, because a class that both defines a transition and
 * moves the value in one change cannot be relied on to animate.
 *
 * Two clocks is the trap this file exists to name. A timeout still fires while the screen is off
 * or the page is behind something; an animation frame does not. So the sweep could run, delete
 * the card's marks and close the row, and THEN the frames arrive on the next wake and mark the
 * card `gone` in a row that no longer has it. Nothing cleared that mark. The next time the same
 * thing came on, its card arrived wearing it -- not faded, because the row's own edge animation
 * outranks the fade, but shifted down and shrunk by the transform that goes with it, until a
 * reload forgot everything. A wall that had rested with a speaker playing came back with the
 * speaker's card a step below its neighbours.
 *
 * So the fade only lands on a card that is still on its way out. A frame that arrives after the
 * sweep finds no `going` mark and does nothing.
 */
export const SHOWN = 620   // read the card off
export const FADE = 340    // then fade it
export const SPARE = 90    // and do not cut the fade short

export type Marks = Record<string, true>

/**
 * Start a card leaving. `going` is set now; `gone` two frames after the beat, if the card is still
 * going; both are cleared and `swept` called once the fade has had its time.
 */
export function leave(id: string, going: Marks, gone: Marks, swept: () => void): void {
  going[id] = true
  setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(() => { if (going[id]) gone[id] = true })), SHOWN)
  setTimeout(() => { delete going[id]; delete gone[id]; swept() }, SHOWN + FADE + SPARE)
}
