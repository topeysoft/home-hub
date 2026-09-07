<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { imageUrl } from './api'
import { store, roomOf } from './store'
import { webrtc, mjpeg, type Live } from './live'
import Icon from './Icon.vue'

/* Full screen for one camera. A still comes up at once; behind it the viewer tries WebRTC, then motion
   JPEG. Whichever plays covers the still and the chip says Live; if neither can, the still keeps
   refreshing and the chip says how old it is. Nothing here says Live unless a picture is moving. */
const dev = computed(() => store.viewer)
const video = ref<HTMLVideoElement>(), moving = ref<HTMLImageElement>()
const src = ref(''), stamp = ref(0), now = ref(Date.now()), loading = ref(true)
const playing = ref(false), trying = ref(false)
let live: Live | null = null

function refresh() { if (dev.value && !playing.value) src.value = imageUrl(dev.value.id) }
const age = computed(() => stamp.value ? Math.round((now.value - stamp.value) / 1000) : null)
const dead = computed(() => dev.value?.state === 'unavailable')
const label = computed(() => {
  if (!dev.value) return ''
  if (dead.value) return 'Offline'
  if (playing.value) return 'Live'
  const still = age.value == null ? 'Loading…' : age.value < 4 ? 'Just now' : `${age.value}s ago`
  return trying.value ? `Connecting · ${still}` : still
})
const place = computed(() => roomOf(dev.value!)?.name ?? '')
function close() { store.viewer = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }

function drop() { live?.stop(); live = null; playing.value = false; trying.value = false }
async function start() {
  drop()
  if (!dev.value || dead.value) return
  const id = dev.value.id
  await nextTick()
  if (!video.value || !moving.value) return
  trying.value = true
  const on = (next: () => void) => ({
    playing: () => { if (store.viewer?.id === id) { playing.value = true; trying.value = false } },
    failed: () => { if (store.viewer?.id === id) { playing.value = false; trying.value = true; next() } },   // a picture that stops falls to the next way
  })
  const stills = () => { live = null; trying.value = false; refresh() }
  const second = () => { live = mjpeg(id, moving.value!, on(stills)) }
  live = 'RTCPeerConnection' in window ? webrtc(id, video.value, on(second)) : mjpeg(id, moving.value, on(stills))
}

let t1: number | undefined, t2: number | undefined
onMounted(() => {
  refresh(); start()
  t1 = window.setInterval(refresh, 4000); t2 = window.setInterval(() => (now.value = Date.now()), 1000)
  window.addEventListener('keydown', key)
})
onUnmounted(() => { drop(); clearInterval(t1); clearInterval(t2); window.removeEventListener('keydown', key) })
watch(dev, () => { src.value = ''; stamp.value = 0; loading.value = true; refresh(); start() })
watch(dead, (d) => { if (d) drop(); else start() })
</script>

<template>
  <div class="viewer" v-if="dev" @click.self="close">
    <div class="viewer-frame" :class="{ loading: loading && !playing, playing }">
      <img v-if="src" class="viewer-still" :src="src" alt="" @load="stamp = Date.now(); loading = false" @error="src = ''" />
      <img ref="moving" class="viewer-moving" alt="" />
      <video ref="video" class="viewer-video" autoplay muted playsinline></video>
      <div class="viewer-veil"></div>
      <header class="viewer-head">
        <div>
          <div class="viewer-name">{{ dev.name }}</div>
          <div class="viewer-sub">{{ place }}<span v-if="place"> · </span>{{ label }}</div>
        </div>
        <button class="round" @click="close" aria-label="Close"><Icon name="close" :size="22" /></button>
      </header>
      <span class="chip viewer-live" :class="{ live: playing }">{{ label }}</span>
    </div>
  </div>
</template>
