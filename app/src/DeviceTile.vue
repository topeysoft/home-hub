<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { act, type Device } from './api'

const props = defineProps<{ device: Device }>()
const emit = defineEmits<{ error: [msg: string] }>()

const cap = computed(() => props.device.capability.split('.')[0])
const active = computed(() => ['on', 'playing', 'open', 'unlocked', 'cleaning'].includes(props.device.state))
const unavailable = computed(() => props.device.state === 'unavailable' || props.device.state === 'unknown')
const detail = computed(() => {
  const d = props.device, a = d.attrs
  if (unavailable.value) return 'Unreachable'
  if (cap.value === 'camera') return d.state === 'streaming' || d.state === 'recording' ? 'Live' : 'Idle'
  if (cap.value === 'media') return d.state === 'playing' ? [a.media_title, a.app_name].filter(Boolean).join(' · ') || 'Playing' : d.state === 'off' ? 'Off' : d.state
  if (cap.value === 'light') return d.state === 'on' ? (a.brightness ? `${Math.round(a.brightness / 2.55)}%` : 'On') : 'Off'
  if (cap.value === 'sensor') return `${d.state}`
  if (cap.value === 'motion') return d.state === 'on' ? 'Motion' : 'Clear'
  if (cap.value === 'contact') return d.state === 'on' ? 'Open' : 'Closed'
  return d.state
})

async function run(action: string, data?: Record<string, unknown>) {
  try { await act(props.device.id, action, data) } catch (e: any) { emit('error', `${props.device.name}: ${e.message}`) }
}
function primary() {
  const d = props.device
  if (cap.value === 'light' || cap.value === 'switch' || cap.value === 'fan') return run(d.state === 'on' ? 'off' : 'on')
  if (cap.value === 'media') return run(d.state === 'playing' ? 'pause' : d.state === 'off' ? 'on' : 'play')
  if (cap.value === 'cover') return run(d.state === 'open' ? 'close' : 'open')
  if (cap.value === 'lock') return run(d.state === 'locked' ? 'unlock' : 'lock')
}
const passive = computed(() => ['sensor', 'motion', 'contact', 'camera'].includes(cap.value))
const imgSrc = ref('')
let timer: number | undefined
function refreshImage() { if (cap.value === 'camera' && !unavailable.value) imgSrc.value = `/devices/${encodeURIComponent(props.device.id)}/image?t=${Date.now()}` }
onMounted(() => { refreshImage(); timer = window.setInterval(refreshImage, 15000) })
onUnmounted(() => clearInterval(timer))
const brightness = computed(() => Math.round((props.device.attrs.brightness ?? 0) / 2.55))
</script>

<template>
  <div class="tile" :class="[cap, { active, passive, unavailable }]">
    <img v-if="cap === 'camera' && imgSrc" class="still" :src="imgSrc" alt="" @error="imgSrc = ''" />
    <button class="tile-main" :disabled="passive || unavailable" @click="primary">
      <span class="cap">{{ cap }}</span>
      <span class="name">{{ device.name }}</span>
      <span class="detail">{{ detail }}</span>
    </button>
    <div class="tile-actions" v-if="cap === 'media' && ['playing', 'paused', 'idle', 'on', 'buffering'].includes(device.state)">
      <button @click="run('off')">Off</button>
    </div>
    <input v-if="cap === 'light' && device.state === 'on'" class="slider" type="range" min="1" max="100" :value="brightness"
           @change="run('on', { brightness_pct: Number(($event.target as HTMLInputElement).value) })" />
  </div>
</template>
