<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The only kind whose instrument is not a control: the picture is what you came for, so the picture
 * is the pane. The panel has always fetched this still — the old pane drew an outline of a camera
 * instead and made you press Watch before it would show you anything.
 *
 * And now it moves. The still is what comes up first, because it is instant and a stream is not, and
 * a moment later the live picture fades in over it -- the viewer's own two ways, WebRTC then motion
 * JPEG, in a smaller frame. What kept streams off this screen was that a wall of cards each holding
 * one open is how a Pi falls over; a sheet is one camera, and only while it is open, so that
 * argument never reached here. What did reach here was the still's own age: once the chip is honest
 * enough to say a cloud camera's picture is four hours old, the next question is why you are being
 * shown it at all.
 *
 * The sheet opens on a hold, including one nobody meant, so nothing is asked of the camera until it
 * has been up for SETTLE -- and the moment it closes, the session goes with it.
 *
 * When it last saw something is along the foot of the pane with every other kind's day, rather than
 * twice: the hub keeps no picture of a sighting, so a second row here would only have repeated the
 * same four times under four empty frames.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { type Device } from '../api'
import { isDead, store } from '../store'
import { ageLabel, fromLive, stillFor, useStill } from '../still'
import { mjpeg, webrtc, type Live } from '../live'
import Icon from '../Icon.vue'

const SETTLE = 800        // how long the sheet must have been open before the camera is woken
const LIVE_EVERY = 5000   // and how often a frame is taken off the live picture, for the cards behind it

const props = defineProps<{ device: Device }>()
const dead = computed(() => isDead(props.device))

const video = ref<HTMLVideoElement>(), moving = ref<HTMLImageElement>()
/* `trying` is a way in, not a look: it rides on the sheet as `.connecting` so a treatment for the
   wait can attach to it. There is a wait to treat -- live.ts gives each way 12s before it gives up,
   and the two are tried in turn, so a camera that is off is 24s of a photograph that does not move.
   The sheet does not claim to be live while it waits, which is why it is not wrong today, only mute. */
const playing = ref(false), trying = ref(false)
let live: Live | null = null
let opening: number | undefined, grab: number | undefined

/* The still is fetched only while nothing is moving: once a picture is playing it IS the picture, and
   asking a cloud camera for a JPEG as well is a call that buys nothing. Shared with the tile behind
   the sheet either way, so opening this never doubles anybody's polling. */
useStill(() => (playing.value || dead.value ? undefined : props.device.id))
/* What is drawn under the video: the newest frame anyone holds, including the ones taken off the live
   picture below -- so closing the sheet leaves what you just watched on the tile behind it. */
const frame = computed(() => stillFor(props.device.id))
const src = computed(() => frame.value.url)
const failed = computed(() => frame.value.failed && !frame.value.url)
/* How old the picture is, where the tag used to say "Idle". Idle was true of the camera and said
   nothing about the frame under it, which is how a four-hour-old picture passed for the present. */
const age = computed(() => (src.value ? ageLabel(frame.value.at) : ''))
/* Nothing here says Live unless a picture is moving -- the viewer's rule, and it has teeth now that
   something on this screen can actually move. HA calling a camera `streaming` is a fact about the
   camera, not about what you are looking at. */
const tag = computed(() =>
  dead.value ? 'Quiet'
  : playing.value ? (props.device.state === 'recording' ? 'Recording' : 'Live')
  /* The wait has to be in WORDS as well as in the bar `.connecting` draws, because the bar is taken
     away under reduced motion and a sheet that then said nothing at all would be back where it
     started. The age stays alongside it: what you are looking at while you wait is still a dated
     photograph, and the waiting does not make it fresher. */
  : trying.value ? (age.value ? `Connecting · ${age.value}` : 'Connecting')
  : age.value || 'Idle')

function drop() {
  live?.stop(); live = null
  playing.value = false; trying.value = false
  clearInterval(grab); grab = undefined
}

/* The viewer's chain, and the viewer's reasons: WebRTC first, so the brain never sees a frame; motion
   JPEG for the cameras and browsers that cannot do it; and the still underneath if neither can. */
async function start() {
  drop()
  if (dead.value) return
  const id = props.device.id
  await nextTick()
  if (!video.value || !moving.value) return
  trying.value = true
  const on = (next: () => void) => ({
    playing: () => { if (props.device.id === id) { playing.value = true; trying.value = false } },
    failed: () => { if (props.device.id === id) { playing.value = false; trying.value = true; next() } },
  })
  const stills = () => { live = null; trying.value = false }    // neither way worked; the still is already underneath
  const second = () => { live = mjpeg(id, moving.value!, on(stills)) }
  live = 'RTCPeerConnection' in window ? webrtc(id, video.value, on(second)) : mjpeg(id, moving.value, on(stills))
}

function later() { clearTimeout(opening); opening = window.setTimeout(start, SETTLE) }
function keepLive() { if (playing.value && video.value) fromLive(props.device.id, video.value) }
watch(playing, (on) => {
  clearInterval(grab); grab = undefined
  if (on) { keepLive(); grab = window.setInterval(keepLive, LIVE_EVERY) }
})

onMounted(later)
onUnmounted(() => { clearTimeout(opening); drop() })
watch(() => props.device.id, () => { drop(); later() })
</script>

<template>
  <div class="rig rig-camera">
    <button class="rig-still" :class="{ playing, connecting: trying && !playing }" @click="store.viewer = device; store.opened = null" :aria-label="`Watch ${device.name}`">
      <img v-if="src" class="rig-still-frame" :src="src" alt="" />
      <img ref="moving" class="rig-still-moving" alt="" />
      <video ref="video" class="rig-still-video" autoplay muted playsinline></video>
      <span class="rig-still-none" v-if="!src && !playing"><Icon name="camera" :size="52" /><span>{{ dead ? 'Not answering' : failed ? 'No picture right now' : 'Looking…' }}</span></span>
      <span class="rig-still-tag" :class="{ live: playing }"><i></i>{{ tag }}</span>
      <span class="rig-still-watch"><Icon name="camera" :size="18" />Watch it full screen</span>
    </button>

</div>
</template>
