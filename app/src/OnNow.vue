<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { Device } from './api'
import { whatsOn, cap, perform, shortName, roomOf, store, notify } from './store'
import Icon from './Icon.vue'

/* Everything that is on across the house, each a chip that turns it off with one tap. The house line says "something is
   on in 3 rooms"; this is the something, and the tap. A door only locks here, never unlocks; a robot has no "off". */
const MAX = 8
const on = computed(whatsOn)

/* A tapped chip leaves the list, because the thing it stood for is not on any more. Going on the tap
   itself reads as a glitch rather than an answer, so it stays where it is for a beat and says what it
   did -- off, closed, locked -- and only then does the row close over it. The rows are held here rather
   than computed straight from `on` for exactly that: a chip on its way out has to keep its place, and a
   list rebuilt from what is still on has no place to keep. */
const SAID = 1100
const said = reactive<Record<string, string>>({})
const rows = ref<Device[]>([])
function sync(now: Device[]) {
  const live = new Map(now.map(d => [d.id, d]))
  const kept: Device[] = []
  for (const d of rows.value) {
    const still = live.get(d.id)
    if (still) { kept.push(still); live.delete(d.id) }
    else if (said[d.id]) kept.push(d)            // gone, but still saying what it did
  }
  rows.value = [...kept, ...live.values()]
}
watch(on, sync, { immediate: true })
const shown = computed(() => rows.value.slice(0, MAX))
const more = computed(() => Math.max(0, on.value.length - MAX))

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
const hint = (d: Device) => { const q = quiet(d); return !q ? '' : q[0] === 'close' ? 'Tap to close' : q[0] === 'lock' ? 'Tap to lock' : 'Tap to turn off' }
/* the chip vanishes once the thing is off, so the toast is the way back: Undo puts it on again. A door stays locked. */
const UNDO: Record<string, [string, string]> = { off: ['on', 'on'], close: ['open', 'open'] }
async function tap(d: Device) {
  const q = quiet(d); if (!q || store.pending[d.id]) return
  /* marked before the house is asked, not after: the state it sets is optimistic too, so by the time the
     round trip is back this thing has already left `on` and the row would have closed over it unmarked. */
  said[d.id] = q[0] === 'close' ? 'Closed' : q[0] === 'lock' ? 'Locked' : 'Off'
  const ok = await perform(d, q[0], undefined, { state: q[1] })
  if (!ok) { delete said[d.id]; sync(on.value); return }
  setTimeout(() => { delete said[d.id]; sync(on.value) }, SAID)
  const back = UNDO[q[0]], name = shortName(d, roomOf(d))
  const line = q[0] === 'close' ? `${name} closing` : q[0] === 'lock' ? `${name} locked` : `${name} off`
  notify(line, 'info', back ? { label: 'Undo', run: () => perform(d, back[0], undefined, { state: back[1] }) } : undefined)
}
</script>

<template>
  <div class="onnow" v-if="on.length" role="group" aria-label="On right now">
    <TransitionGroup name="onnow">
      <button v-for="d in shown" :key="d.id" class="onnow-chip" :class="[cap(d), { fixed: !quiet(d), pending: store.pending[d.id], said: !!said[d.id] }]"
              :disabled="!quiet(d) || !!said[d.id]" :title="hint(d)"
              :aria-label="said[d.id] ? `${what(d)} in the ${place(d)}. ${said[d.id]}.` : `${what(d)} in the ${place(d)}. ${hint(d)}`" @click="tap(d)"
              v-hold="() => (store.opened = d)">
        <span class="onnow-icon"><Icon :name="said[d.id] ? 'check' : cap(d)" :size="16" /></span>
        <span class="onnow-text"><span class="onnow-name">{{ what(d) }}</span><span class="onnow-place">{{ said[d.id] || place(d) }}</span></span>
      </button>
    </TransitionGroup>
    <span class="onnow-more" v-if="more > 0">and {{ more }} more</span>
  </div>
</template>
