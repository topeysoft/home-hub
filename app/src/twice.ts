// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What the panel asks twice about.
 *
 * Almost everything here happens on one tap, and that is the product: a tile is
 * a switch on a wall, and a switch on a wall does not interview you. The two
 * exceptions are the two where the failure mode of a stray finger is not a
 * lamp -- opening a way into the house, and making a noise nobody can take
 * back. docs/voice.md already says the shape of this rule for sentences:
 * "the direction matters more than the device", and closing and locking are
 * free because the failure mode of a misheard "close the garage" is a closed
 * garage. This is that rule for fingers.
 *
 * The second tap is not a confirmation dialogue and must not become one.
 * health.py says why: "Are you sure?" is not a question anybody can answer. The
 * tile stays where it is, says what the next tap will do, and forgets in three
 * seconds -- so the cost to somebody who meant it is one more tap in the same
 * place, and the cost to somebody who did not is nothing at all.
 *
 * Only ONE direction of each pair is in here. Locking, and silencing, are
 * always one tap: a house made safer or quieter should never be made to wait.
 */

import { ref } from 'vue'

/** How long an armed tile stays armed. Long enough to be a second tap, short enough
    that a tile left armed on a wall is not a loaded button an hour later. */
export const ARM_FOR = 3000

const ASKS: Record<string, { action: string; armed: string }> = {
  lock: { action: 'unlock', armed: 'Tap again to unlock' },     // a door opens on the second tap, never the first
  alarm: { action: 'on', armed: 'Tap again to sound' },
}

/** The words an armed control shows, or null where this one just does it.
    `kind` is what the thing is SHOWN as (store.cap), never the driver's word:
    a siren is a `switch` entity, and being told it is an alarm is the whole point. */
export function asksTwice(kind: string, action: string): string | null {
  const ask = ASKS[kind]
  return ask && ask.action === action ? ask.armed : null
}

/** One armed control. Three things hold one -- the tile, the pane's verb row, and the
    instrument under it -- and they share this rather than each keeping a boolean, because
    three copies of "did they tap it already" is three chances for one of them to be the
    way round the rule. `armed` is the words to show while it waits, or null. */
export function useArm() {
  const armed = ref<string | null>(null)
  let timer: number | undefined
  function clear() { armed.value = null; clearTimeout(timer) }
  /** Do it, or arm and wait for the second tap. True when it actually ran. */
  function tap(kind: string, action: string, go: () => void): boolean {
    const label = asksTwice(kind, action)
    if (label && armed.value !== label) {
      armed.value = label; clearTimeout(timer); timer = window.setTimeout(clear, ARM_FOR)
      return false
    }
    clear(); go()
    return true
  }
  return { armed, tap, clear }
}
