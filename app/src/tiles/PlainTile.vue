<script setup lang="ts">
import { computed } from 'vue'
import { act, type Device } from '../api'
import { cap, isActive } from '../store'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const emit = defineEmits<{ error: [msg: string] }>()
const kind = computed(() => cap(props.device))
const on = computed(() => isActive(props.device))
const dead = computed(() => props.device.state === 'unavailable' || props.device.state === 'unknown')
const passive = computed(() => ['sensor', 'motion', 'contact'].includes(kind.value))

const label = computed(() => {
  const d = props.device, k = kind.value
  if (dead.value) return 'Unreachable'
  if (k === 'sensor') {
    const cls = d.capability.split('.')[1]
    const unit = cls === 'temperature' ? '°' : cls === 'humidity' ? '%' : cls === 'illuminance' ? ' lx' : ''
    return `${Math.round(Number(d.state))}${unit}`
  }
  if (k === 'motion') return d.state === 'on' ? 'Motion' : 'Clear'
  if (k === 'contact') return d.state === 'on' ? 'Open' : 'Closed'
  if (k === 'lock') return d.state === 'locked' ? 'Locked' : d.state === 'unlocked' ? 'Unlocked' : d.state
  if (k === 'cover') return d.attrs.current_position != null && d.state === 'open' ? `${d.attrs.current_position}% open` : d.state === 'open' ? 'Open' : 'Closed'
  if (k === 'fan') return d.state === 'on' ? (d.attrs.percentage ? `${d.attrs.percentage}%` : 'On') : 'Off'
  return d.state === 'on' ? 'On' : 'Off'
})
const next = computed(() => {
  const d = props.device, k = kind.value
  if (k === 'cover') return d.state === 'open' ? 'close' : 'open'
  if (k === 'lock') return d.state === 'locked' ? 'unlock' : 'lock'
  return d.state === 'on' ? 'off' : 'on'
})
async function tap() {
  if (passive.value || dead.value) return
  try { await act(props.device.id, next.value) } catch (e: any) { emit('error', `${props.device.name}: ${e.message}`) }
}
</script>

<template>
  <button class="tile plain" :class="[kind, { on, dead, passive }]" :disabled="passive || dead" @click="tap">
    <div class="tile-body">
      <span class="tile-icon"><Icon :name="kind" /></span>
      <span class="tile-name">{{ device.name }}</span>
      <span class="tile-state" :class="{ big: kind === 'sensor' }">{{ label }}</span>
    </div>
  </button>
</template>
