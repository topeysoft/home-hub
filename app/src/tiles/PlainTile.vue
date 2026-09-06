<script setup lang="ts">
import { computed } from 'vue'
import type { Device } from '../api'
import { cap, isActive, isDead, perform, shortName, roomOf, store } from '../store'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const kind = computed(() => cap(props.device))
const on = computed(() => isActive(props.device))
const dead = computed(() => isDead(props.device))
const pending = computed(() => !!store.pending[props.device.id])
const passive = computed(() => ['sensor', 'motion', 'contact'].includes(kind.value))
const name = computed(() => shortName(props.device, roomOf(props.device)))

const label = computed(() => {
  const d = props.device, k = kind.value
  if (dead.value) return 'Not responding'
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
  if (k === 'vacuum') return d.state === 'cleaning' ? 'Cleaning' : d.state === 'docked' ? 'Docked' : d.state
  return d.state === 'on' ? 'On' : 'Off'
})
const next = computed<[string, string]>(() => {
  const d = props.device, k = kind.value
  if (k === 'cover') return d.state === 'open' ? ['close', 'closed'] : ['open', 'open']
  if (k === 'lock') return d.state === 'locked' ? ['unlock', 'unlocked'] : ['lock', 'locked']
  return d.state === 'on' ? ['off', 'off'] : ['on', 'on']
})
function tap() {
  if (passive.value || dead.value) return
  const [action, state] = next.value
  perform(props.device, action, undefined, { state })
}
</script>

<template>
  <button class="tile plain" :class="[kind, { on, dead, passive, pending }]" :disabled="passive || dead" @click="tap" :aria-pressed="passive ? undefined : on">
    <div class="tile-body">
      <span class="tile-icon"><Icon :name="kind" /></span>
      <span class="tile-name">{{ name }}</span>
      <span class="tile-state" :class="{ big: kind === 'sensor' }">{{ label }}</span>
    </div>
  </button>
</template>
