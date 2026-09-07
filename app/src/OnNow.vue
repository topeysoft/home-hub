<script setup lang="ts">
import { computed } from 'vue'
import type { Device } from './api'
import { whatsOn, cap, perform, shortName, roomOf, store } from './store'
import Icon from './Icon.vue'

/* Everything that is on across the house, each a chip that turns it off with one tap. The house line says "something is
   on in 3 rooms"; this is the something, and the tap. A door only locks here, never unlocks; a robot has no "off". */
const MAX = 8
const on = computed(whatsOn)
const shown = computed(() => on.value.slice(0, MAX))
const more = computed(() => on.value.length - shown.value.length)

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
function tap(d: Device) {
  const q = quiet(d); if (!q || store.pending[d.id]) return
  perform(d, q[0], undefined, { state: q[1] })
}
</script>

<template>
  <div class="onnow" v-if="on.length" role="group" aria-label="On right now">
    <button v-for="d in shown" :key="d.id" class="onnow-chip" :class="[cap(d), { fixed: !quiet(d), pending: store.pending[d.id] }]"
            :disabled="!quiet(d)" :title="hint(d)" :aria-label="`${what(d)} in the ${place(d)}. ${hint(d)}`" @click="tap(d)">
      <span class="onnow-icon"><Icon :name="cap(d)" :size="16" /></span>
      <span class="onnow-text"><span class="onnow-name">{{ what(d) }}</span><span class="onnow-place">{{ place(d) }}</span></span>
    </button>
    <span class="onnow-more" v-if="more > 0">and {{ more }} more</span>
  </div>
</template>
