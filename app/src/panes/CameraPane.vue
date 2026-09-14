<script setup lang="ts">
/*
 * The only kind whose instrument is not a control: the picture is what you came for, so the picture
 * is the pane. The panel has always fetched this still — the old pane drew an outline of a camera
 * instead and made you press Watch before it would show you anything.
 *
 * When it last saw something is along the foot of the pane with every other kind's day, rather than
 * twice: the hub keeps no picture of a sighting, so a second row here would only have repeated the
 * same four times under four empty frames.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { imageUrl, type Device } from '../api'
import { isDead, store } from '../store'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const dead = computed(() => isDead(props.device))
const live = computed(() => props.device.state === 'recording' || props.device.state === 'streaming')
const src = ref(imageUrl(props.device.id))
const failed = ref(false)

/* A still, refreshed while the pane is open. Slow on purpose: this is a picture to glance at, and
   the viewer next door is what a live stream is for. */
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => { if (!failed.value) src.value = imageUrl(props.device.id) }, 5000) })
onUnmounted(() => clearInterval(tick))
</script>

<template>
  <div class="rig rig-camera">
    <button class="rig-still" @click="store.viewer = device; store.opened = null" :aria-label="`Watch ${device.name}`">
      <img v-if="!failed" :src="src" alt="" @error="failed = true" />
      <span class="rig-still-none" v-else><Icon name="camera" :size="52" /><span>{{ dead ? 'Not answering' : 'No picture right now' }}</span></span>
      <span class="rig-still-tag" :class="{ live }"><i></i>{{ dead ? 'Quiet' : live ? (device.state === 'recording' ? 'Recording' : 'Live') : 'Idle' }}</span>
      <span class="rig-still-watch"><Icon name="camera" :size="18" />Watch it full screen</span>
    </button>

</div>
</template>
