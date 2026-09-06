<script setup lang="ts">
import { computed, ref } from 'vue'
import { act, type Device } from '../api'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const emit = defineEmits<{ error: [msg: string] }>()

const on = computed(() => props.device.state === 'on')
const dead = computed(() => props.device.state === 'unavailable')
const dimmable = computed(() => !!(props.device.attrs.supported_color_modes ?? []).some((m: string) => m !== 'onoff'))
const live = computed(() => Math.round((props.device.attrs.brightness ?? 0) / 2.55))
const preview = ref<number | null>(null)
const pct = computed(() => preview.value ?? (on.value ? live.value || 100 : 0))
const label = computed(() => dead.value ? 'Unreachable' : !on.value ? 'Off' : dimmable.value ? `${pct.value}%` : 'On')

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
  try {
    if (dragging && preview.value != null) await act(props.device.id, 'on', { brightness_pct: preview.value })
    else await act(props.device.id, on.value ? 'off' : 'on')
  } catch (e: any) { emit('error', `${props.device.name}: ${e.message}`) }
  finally { el = null; setTimeout(() => (preview.value = null), 600) }
}
</script>

<template>
  <div class="tile light" :class="{ on, dead, dimmable }" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
    <div class="fill" :style="{ width: pct + '%' }"></div>
    <div class="tile-body">
      <span class="tile-icon"><Icon name="light" /></span>
      <span class="tile-name">{{ device.name }}</span>
      <span class="tile-state">{{ label }}</span>
    </div>
  </div>
</template>
