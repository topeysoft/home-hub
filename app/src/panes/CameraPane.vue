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
import { computed } from 'vue'
import { type Device } from '../api'
import { isDead, store } from '../store'
import { ageLabel, useStill } from '../still'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const dead = computed(() => isDead(props.device))
const live = computed(() => props.device.state === 'recording' || props.device.state === 'streaming')
/* A still, refreshed while the pane is open -- shared with the tile behind the pane, so opening one
   does not start a second fetch of the same camera. Slow on purpose, and slower still while the
   picture is not changing: this is a picture to glance at, and the viewer next door is the live one. */
const still = useStill(() => props.device.id)
const src = computed(() => still.value.url)
const failed = computed(() => still.value.failed && !still.value.url)
/* How old the picture is, where the tag used to say "Idle". Idle was true of the camera and said
   nothing about the frame under it, which is how a four-hour-old picture passed for the present. */
const age = computed(() => still.value.url ? ageLabel(still.value.at) : '')
</script>

<template>
  <div class="rig rig-camera">
    <button class="rig-still" @click="store.viewer = device; store.opened = null" :aria-label="`Watch ${device.name}`">
      <img v-if="src" :src="src" alt="" />
      <span class="rig-still-none" v-else><Icon name="camera" :size="52" /><span>{{ dead ? 'Not answering' : failed ? 'No picture right now' : 'Looking…' }}</span></span>
      <span class="rig-still-tag" :class="{ live }"><i></i>{{ dead ? 'Quiet' : live ? (device.state === 'recording' ? 'Recording' : 'Live') : age || 'Idle' }}</span>
      <span class="rig-still-watch"><Icon name="camera" :size="18" />Watch it full screen</span>
    </button>

</div>
</template>
