<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { imageUrl } from './api'
import { store, roomOf } from './store'
import Icon from './Icon.vue'

const dev = computed(() => store.viewer)
const src = ref(''), stamp = ref(0), now = ref(Date.now()), loading = ref(true)
function refresh() { if (dev.value) src.value = imageUrl(dev.value.id) }
const age = computed(() => stamp.value ? Math.round((now.value - stamp.value) / 1000) : null)
const label = computed(() => {
  if (!dev.value) return ''
  if (dev.value.state === 'unavailable') return 'Offline'
  if (dev.value.state === 'recording') return 'Recording'
  return age.value == null ? 'Loading…' : age.value < 4 ? 'Just now' : `${age.value}s ago`
})
const place = computed(() => roomOf(dev.value!)?.name ?? '')
function close() { store.viewer = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
let t1: number | undefined, t2: number | undefined
onMounted(() => {
  refresh(); t1 = window.setInterval(refresh, 4000); t2 = window.setInterval(() => (now.value = Date.now()), 1000)
  window.addEventListener('keydown', key)
})
onUnmounted(() => { clearInterval(t1); clearInterval(t2); window.removeEventListener('keydown', key) })
watch(dev, () => { src.value = ''; stamp.value = 0; loading.value = true; refresh() })
</script>

<template>
  <div class="viewer" v-if="dev" @click.self="close">
    <div class="viewer-frame" :class="{ loading }">
      <img v-if="src" :src="src" alt="" @load="stamp = Date.now(); loading = false" @error="src = ''" />
      <div class="viewer-veil"></div>
      <header class="viewer-head">
        <div>
          <div class="viewer-name display">{{ dev.name }}</div>
          <div class="viewer-sub">{{ place }}<span v-if="place"> · </span>{{ label }}</div>
        </div>
        <button class="round" @click="close" aria-label="Close"><Icon name="close" :size="22" /></button>
      </header>
      <span class="chip viewer-live" :class="{ live: dev.state === 'recording' || dev.state === 'streaming' }">{{ label }}</span>
    </div>
  </div>
</template>
