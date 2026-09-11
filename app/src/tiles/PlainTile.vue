<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Device } from '../api'
import { cap, isActive, isDead, perform, shortName, roomOf, store } from '../store'
import { readingLabel } from '../readings'
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
  if (passive.value) return readingLabel(d)
  if (k === 'lock') return arming.value ? 'Tap again to unlock' : d.state === 'locked' ? 'Locked' : d.state === 'unlocked' ? 'Unlocked' : d.state
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
const arming = ref(false)
let armTimer: number | undefined
function tap() {
  if (passive.value || dead.value) return
  const [action, state] = next.value
  if (action === 'unlock' && !arming.value) {                // a door opens on the second tap, never the first
    arming.value = true; clearTimeout(armTimer); armTimer = window.setTimeout(() => (arming.value = false), 3000); return
  }
  arming.value = false; clearTimeout(armTimer)
  perform(props.device, action, undefined, { state })
}
</script>

<template>
  <button class="tile plain" :class="[kind, { on, dead, passive, pending, arming }]" :disabled="passive || dead" @click="tap" :aria-pressed="passive ? undefined : on">
    <!-- no artwork of its own, so the icon, oversized and faint, is the art: a shelf of no-name plugs reads composed rather than empty -->
    <span class="tile-art" aria-hidden="true"><Icon :name="kind" :size="150" /></span>
    <span class="tile-maker" v-if="device.maker">{{ device.maker }}</span>
    <div class="tile-body">
      <span class="tile-icon"><Icon :name="kind" /></span>
      <span class="tile-name">{{ name }}</span>
      <span class="tile-state" :class="{ big: kind === 'sensor' }">{{ label }}</span>
    </div>
  </button>
</template>
