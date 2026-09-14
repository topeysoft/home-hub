<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, roomOf, deviceById, perform } from './store'
import { webrtc, mjpeg, type Live } from './live'
import { ageLabel, fromLive, useStill } from './still'
import Icon from './Icon.vue'

/* Full screen for one camera. A still comes up at once; behind it the viewer tries WebRTC, then motion
   JPEG. Whichever plays covers the still and the chip says Live; if neither can, the still keeps
   refreshing and the chip says how old the frame is -- its own age, not the age of our last fetch,
   which for a camera that hands out one frame a night is the whole difference. Nothing here says Live
   unless a picture is moving.
   Sound comes with WebRTC and starts muted, as browsers insist; a speaker button turns it on. A camera
   with a lamp built in (Ring's floodlight and spotlight cams) gets a light button beside it.

   While it plays, a frame is copied out of the video every few seconds and left where the cards can
   find it. A cloud camera's still route only ever returns the last thing it recorded, so this is the
   one current picture of the house there is: glance at the doorbell and the card behind you stops
   showing last night. */
const LIVE_EVERY = 5000        // how often a frame is copied out of the moving picture for the cards
const dev = computed(() => store.viewer)
const video = ref<HTMLVideoElement>(), moving = ref<HTMLImageElement>()
const loading = ref(true)
const playing = ref(false), trying = ref(false), audio = ref(false), sound = ref(false)
let live: Live | null = null

/* The still is asked for more often here than on a card -- this is the screen somebody is standing in
   front of -- and only while nothing is moving. It backs off on its own while the frame does not change. */
const still = useStill(() => playing.value ? undefined : dev.value?.id, 4000)
const src = computed(() => still.value.url)
watch(src, () => { if (src.value) loading.value = false })
const dead = computed(() => dev.value?.state === 'unavailable')
const label = computed(() => {
  if (!dev.value) return ''
  if (dead.value) return 'Offline'
  if (playing.value) return 'Live'
  const age = src.value ? ageLabel(still.value.at) : 'Loading…'
  return trying.value ? `Connecting · ${age}` : age
})
const place = computed(() => roomOf(dev.value!)?.name ?? '')
const lamp = computed(() => { const l = dev.value?.attrs?.light ? deviceById(dev.value.attrs.light) : undefined; return l && l.state !== 'unavailable' ? l : undefined })
const lampOn = computed(() => lamp.value?.state === 'on')
const lampBusy = computed(() => !!lamp.value && !!store.pending[lamp.value.id])
function toggleLamp() { if (lamp.value && !lampBusy.value) perform(lamp.value, lampOn.value ? 'off' : 'on', undefined, { state: lampOn.value ? 'off' : 'on' }) }
function close() { store.viewer = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }

function drop() { live?.stop(); live = null; playing.value = false; trying.value = false; audio.value = false; hush() }
function hush() { sound.value = false; if (video.value) video.value.muted = true }
function toggleSound() { if (!video.value) return; sound.value = !sound.value; video.value.muted = !sound.value }
async function start() {
  drop()
  if (!dev.value || dead.value) return
  const id = dev.value.id
  await nextTick()
  if (!video.value || !moving.value) return
  trying.value = true
  const on = (next: () => void) => ({
    playing: () => { if (store.viewer?.id === id) { playing.value = true; trying.value = false } },
    failed: () => { if (store.viewer?.id === id) { playing.value = false; trying.value = true; audio.value = false; hush(); next() } },   // a picture that stops falls to the next way
    audio: () => { if (store.viewer?.id === id) audio.value = true },
  })
  // Neither moving picture could be had: the still is already being watched underneath, so stop trying.
  const stills = () => { live = null; trying.value = false }
  const second = () => { live = mjpeg(id, moving.value!, on(stills)) }
  live = 'RTCPeerConnection' in window ? webrtc(id, video.value, on(second)) : mjpeg(id, moving.value, on(stills))
}

/* One frame out of the live picture, kept where every card showing this camera can find it. Every few
   seconds rather than every frame: it costs a canvas draw and a JPEG, and a card is a glance. */
let grab: number | undefined
function keepLive() { if (playing.value && dev.value && video.value) fromLive(dev.value.id, video.value) }
watch(playing, (on) => {
  clearInterval(grab); grab = undefined
  if (on) { keepLive(); grab = window.setInterval(keepLive, LIVE_EVERY) }
})

onMounted(() => {
  start()
  window.addEventListener('keydown', key)
})
onUnmounted(() => { drop(); clearInterval(grab); window.removeEventListener('keydown', key) })
watch(dev, () => { loading.value = true; start() })
watch(dead, (d) => { if (d) drop(); else start() })
</script>

<template>
  <div class="viewer" v-if="dev" @click.self="close">
    <div class="viewer-frame" :class="{ loading: loading && !playing, playing }">
      <img v-if="src" class="viewer-still" :src="src" alt="" />
      <img ref="moving" class="viewer-moving" alt="" />
      <video ref="video" class="viewer-video" autoplay muted playsinline></video>
      <div class="viewer-veil"></div>
      <header class="viewer-head">
        <div>
          <div class="viewer-name">{{ dev.name }}</div>
          <div class="viewer-sub">{{ place }}<span v-if="place"> · </span>{{ label }}</div>
        </div>
        <div class="viewer-actions">
          <button v-if="lamp" class="round" :class="{ on: lampOn, busy: lampBusy }" @click="toggleLamp" :aria-label="lampOn ? 'Light off' : 'Light on'" :aria-pressed="lampOn"><Icon name="light" :size="22" /></button>
          <button v-if="playing && audio" class="round" :class="{ on: sound }" @click="toggleSound" :aria-label="sound ? 'Mute' : 'Sound on'" :aria-pressed="sound"><Icon :name="sound ? 'volume' : 'mute'" :size="22" /></button>
          <button class="round" @click="close" aria-label="Close"><Icon name="close" :size="22" /></button>
        </div>
      </header>
      <span class="chip viewer-live" :class="{ live: playing }">{{ label }}</span>
    </div>
  </div>
</template>
