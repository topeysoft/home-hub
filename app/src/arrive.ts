// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * A screen arriving: hold everything a step off its place, then let it come in,
 * one card after another.
 *
 * The Home row has done this since it was drawn -- first load, waking from rest,
 * coming back from a room -- and it is the panel's one entrance. This is that
 * mechanism, lifted out so the Rooms and Cameras tabs can have it without a
 * second copy of the timing drifting away from the first. BentoRow.vue still
 * carries its own; it predates this and should adopt it next time it is opened.
 *
 * Two frames, and both are load-bearing. `set` puts the cards off their place
 * with no transition on them; the double rAF is what guarantees the browser has
 * PAINTED that state before `go` turns the transition on, because a class added
 * and removed inside one frame animates nothing at all. The settle afterwards
 * takes the classes off again, so a card that is home carries nothing -- a held
 * card, a dimmer drag and the edge fades all behave as if this had never
 * happened.
 *
 * WHAT ARRIVES is not decided here. Under reduced motion the stylesheet cancels
 * the travel and leaves a short fade, and this still arms exactly as it does
 * otherwise -- deciding what a move becomes belongs in one place, and that place
 * is the stylesheet. Arming it in both cases is what stops the two drifting
 * apart.
 */
import { onMounted, onUnmounted, ref, watch, type Ref } from 'vue'

export type Flow = '' | 'set' | 'go'

/**
 * @param empty  nothing to arrive: an empty screen must not be left at opacity 0
 * @param woke   how many times the panel has come back from rest, so it arrives again
 * @param settle how long until the classes come off; past the last card's wait plus its travel
 */
export function useArrive(empty: () => boolean, woke: () => number | undefined, settle = 1300): Ref<Flow> {
  const flow = ref<Flow>('')
  let timer: number | undefined
  function arrive() {
    if (empty()) return
    flow.value = 'set'
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (flow.value !== 'set') return
      flow.value = 'go'
      clearTimeout(timer)
      timer = window.setTimeout(() => (flow.value = ''), settle)
    }))
  }
  onMounted(arrive)
  watch(woke, arrive)
  onUnmounted(() => clearTimeout(timer))
  return flow
}
