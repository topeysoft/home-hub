<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Device } from './api'
import { whatsOn, cap, done, doneLine, isActive, justDone, perform, shortName, roomOf, store } from './store'
import Icon from './Icon.vue'

/* Everything that is on across the house, each a chip that turns it off with one tap. The house line says "something is
   on in 3 rooms"; this is the something, and the tap. A door only locks here, never unlocks; a robot has no "off". */
const MAX = 8
const on = computed(whatsOn)

/* A tapped chip does NOT leave the list. It keeps its place, says what it did and when -- "Off · just now" -- and
   tapping it again puts the thing back, which is where the undo lives; a chip going out from under the finger that
   touched it is the wrong answer to "did that work", and the row closing over the gap moves every other chip under the
   hand as well. What clears them is the panel looking away: store.ts (`done`) says what that means, App.vue says when.
   The rows are held here rather than computed straight from `on` for exactly that -- a chip that has been quieted has to
   keep its place, and a list rebuilt from what is still on has no place to keep. */
const rows = ref<Device[]>([])
function sync(now: Device[]) {
  const rest = new Map(now.map(d => [d.id, d]))
  const kept: Device[] = []
  for (const d of rows.value) {
    const still = rest.get(d.id)
    if (still) { kept.push(still); rest.delete(d.id) }
    else if (done[d.id]) kept.push(d)                // off, and still saying so
  }
  /* quieted somewhere else, or before Home was come back to: still this person's own doing, so still here */
  const held = new Set([...kept, ...rest.values()].map(d => d.id))
  rows.value = [...kept, ...rest.values(), ...justDone().filter(d => !held.has(d.id))]
}
watch(on, sync, { immediate: true })
watch(() => Object.keys(done).length, () => sync(on.value))

const tick = ref(Date.now())   // so "just now" does not sit there for an hour
let minute: number | undefined
onMounted(() => (minute = window.setInterval(() => (tick.value = Date.now()), 30000)))
onUnmounted(() => clearInterval(minute))

const shown = computed(() => rows.value.slice(0, MAX))
const more = computed(() => Math.max(0, on.value.length - shown.value.filter(d => isActive(d)).length))

const place = (d: Device) => roomOf(d)?.name ?? ''
function what(d: Device): string {
  const k = cap(d)
  if (k === 'media') return d.attrs.media_title ? `${shortName(d, roomOf(d))}, ${d.attrs.media_title}` : shortName(d, roomOf(d))
  return shortName(d, roomOf(d))
}
/* the action that quiets each thing, and the state to show while the house confirms it */
function quiet(d: Device): [string, string] | null {
  const k = cap(d)
  if (k === 'cover') return ['close', 'closed']
  if (k === 'lock') return ['lock', 'locked']
  if (['light', 'switch', 'fan', 'media', 'climate'].includes(k)) return ['off', 'off']
  return null
}
/* and the way back from each, for a chip that is standing there saying it did one. A door is not on this
   list on purpose: the house locks from here and unlocks at the door, so a stray tap cannot open it. */
const BACK: Record<string, [string, string]> = { Off: ['on', 'on'], Closed: ['open', 'open'], Paused: ['play', 'playing'] }
const kept = (d: Device) => !!done[d.id] && !isActive(d)
const back = (d: Device) => kept(d) ? BACK[done[d.id].verb] ?? null : null
const line = (d: Device) => kept(d) ? doneLine(d.id, tick.value) : place(d)
function hint(d: Device): string {
  if (kept(d)) { const b = back(d); return !b ? '' : b[0] === 'open' ? 'Tap to open' : b[0] === 'play' ? 'Tap to play' : 'Tap to turn back on' }
  const q = quiet(d); return !q ? '' : q[0] === 'close' ? 'Tap to close' : q[0] === 'lock' ? 'Tap to lock' : 'Tap to turn off'
}
const dead = (d: Device) => kept(d) ? !back(d) : !quiet(d)
async function tap(d: Device) {
  if (store.pending[d.id]) return
  /* The chip says what happened, so there is no toast to say it again -- and the chip is the undo, which
     is what a toast used to carry out of the room after six seconds. */
  const go = kept(d) ? back(d) : quiet(d)
  if (go) await perform(d, go[0], undefined, { state: go[1] })
}
</script>

<template>
  <div class="onnow" v-if="rows.length" role="group" aria-label="On right now">
    <TransitionGroup name="onnow">
      <button v-for="d in shown" :key="d.id" class="onnow-chip" :class="[cap(d), { fixed: dead(d), pending: store.pending[d.id], kept: kept(d) }]"
              :disabled="dead(d)" :title="hint(d)"
              :aria-label="`${what(d)} in the ${place(d)}. ${kept(d) ? line(d) + '.' : ''} ${hint(d)}`.replace(/\s+/g, ' ').trim()" @click="tap(d)"
              v-hold="() => (store.opened = d)">
        <span class="onnow-icon"><Icon :name="kept(d) ? 'check' : cap(d)" :size="16" /></span>
        <span class="onnow-text"><span class="onnow-name">{{ what(d) }}</span><span class="onnow-place">{{ line(d) }}</span></span>
      </button>
    </TransitionGroup>
    <span class="onnow-more" v-if="more > 0">and {{ more }} more</span>
  </div>
</template>
