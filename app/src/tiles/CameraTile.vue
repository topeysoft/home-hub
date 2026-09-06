<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { imageUrl, type Device } from '../api'
import { store, roomOf } from '../store'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device; compact?: boolean }>()
const dead = computed(() => props.device.state === 'unavailable')
const live = computed(() => props.device.state === 'streaming' || props.device.state === 'recording')
const src = ref(''), stamp = ref(0), now = ref(Date.now())
function refresh() { if (!dead.value && !document.hidden) src.value = imageUrl(props.device.id) }
const age = computed(() => stamp.value ? Math.max(0, Math.round((now.value - stamp.value) / 1000)) : null)
const ageLabel = computed(() => age.value == null ? '' : age.value < 5 ? 'Just now' : age.value < 60 ? `${age.value}s ago` : `${Math.round(age.value / 60)}m ago`)
const place = computed(() => props.compact ? roomOf(props.device)?.name : '')
let t1: number | undefined, t2: number | undefined
onMounted(() => { refresh(); t1 = window.setInterval(refresh, 15000); t2 = window.setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => { clearInterval(t1); clearInterval(t2) })
</script>

<template>
  <button class="tile camera wide" :class="{ dead, live, compact }" @click="store.viewer = device" :aria-label="`Open ${device.name} camera`">
    <img v-if="src" :src="src" alt="" @load="stamp = Date.now()" @error="src = ''" />
    <div class="camera-veil"></div>
    <div class="camera-top">
      <span class="chip" :class="{ live }">{{ dead ? 'Offline' : live ? 'Live' : ageLabel || 'Loading' }}</span>
    </div>
    <div class="camera-bottom">
      <span class="tile-icon"><Icon name="camera" :size="18" /></span>
      <span class="camera-text">
        <span class="tile-name">{{ device.name }}</span>
        <span class="camera-place" v-if="place">{{ place }}</span>
      </span>
    </div>
  </button>
</template>
