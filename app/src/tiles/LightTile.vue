<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Device } from '../api'
import { perform, shortName, roomOf, store, isDead } from '../store'
import Icon from '../Icon.vue'
import DeviceArt from '../DeviceArt.vue'
import { lightKind } from '../art'

const props = defineProps<{ device: Device }>()
const on = computed(() => props.device.state === 'on')
const dead = computed(() => isDead(props.device))
const pending = computed(() => !!store.pending[props.device.id])
const dimmable = computed(() => !!(props.device.attrs.supported_color_modes ?? []).some((m: string) => m !== 'onoff'))
const live = computed(() => Math.round((props.device.attrs.brightness ?? 0) / 2.55))
const preview = ref<number | null>(null)
const pct = computed(() => preview.value ?? (on.value ? live.value || 100 : 0))
const name = computed(() => shortName(props.device, roomOf(props.device)))
/* Which drawing this light gets. A guess off the name for now -- see lightKind's
   own note; the real answer is a per-device setting nobody has been asked for yet. */
const kind = computed(() => lightKind(props.device.name || name.value))
const hintSeen = ref(safe(() => localStorage.getItem('dim-hint') === '1'))
function safe<T>(f: () => T): T | false { try { return f() } catch { return false } }
const label = computed(() => {
  if (dead.value) return 'Not responding'
  if (!on.value) return 'Off'
  if (!dimmable.value) return 'On'
  return hintSeen.value ? `${pct.value}%` : `${pct.value}% · slide to dim`
})

let startX = 0, dragging = false, el: HTMLElement | null = null
function down(e: PointerEvent) {
  if (dead.value) return
  el = e.currentTarget as HTMLElement; el.setPointerCapture(e.pointerId); startX = e.clientX; dragging = false
}
function move(e: PointerEvent) {
  if (!el || !dimmable.value) return
  if (!dragging && Math.abs(e.clientX - startX) > 8) dragging = true
  if (dragging) {
    const r = el.getBoundingClientRect()
    preview.value = Math.min(100, Math.max(1, Math.round(((e.clientX - r.left) / r.width) * 100)))
  }
}
async function up() {
  if (!el) return
  el = null
  const d = props.device
  if (dragging && preview.value != null) {
    hintSeen.value = true; safe(() => localStorage.setItem('dim-hint', '1'))
    await perform(d, 'on', { brightness_pct: preview.value }, { state: 'on', attrs: { brightness: Math.round(preview.value * 2.55) } })
  } else {
    await perform(d, on.value ? 'off' : 'on', undefined, { state: on.value ? 'off' : 'on' })
  }
  preview.value = null
}
</script>

<template>
  <div class="tile light" :class="{ on, dead, dimmable, pending }" role="button" :aria-label="`${name}, ${label}`" :aria-pressed="on"
       tabindex="0" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @keydown.enter.space.prevent="perform(device, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' })">
    <div class="fill" :style="{ width: pct + '%' }"></div>
    <DeviceArt :kind="kind" :state="{ on, brightness: pct / 100 }" />
    <span class="tile-maker" v-if="device.maker">{{ device.maker }}</span>
    <div class="tile-body">
      <span class="tile-icon"><Icon name="light" /></span>
      <span class="tile-name">{{ name }}</span>
      <span class="tile-state">{{ label }}</span>
    </div>
  </div>
</template>
