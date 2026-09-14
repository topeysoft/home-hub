<script setup lang="ts">
import { computed } from 'vue'
import { type Device } from '../api'
import { store, roomOf } from '../store'
import Icon from '../Icon.vue'
import DeviceArt from '../DeviceArt.vue'
import { kindFor } from '../art'
import { ageLabel, useStill } from '../still'

const props = defineProps<{ device: Device; compact?: boolean }>()
const dead = computed(() => props.device.state === 'unavailable')
const live = computed(() => props.device.state === 'recording')   // a tile shows stills, so the only honest red chip is Recording
/* The picture, and how old it really is -- not how long ago we fetched it. A camera that hands out
   the same frame all night says so on the chip rather than claiming a new one every fifteen seconds. */
const still = useStill(() => dead.value ? undefined : props.device.id)
const src = computed(() => still.value.url)
const age = computed(() => src.value ? ageLabel(still.value.at) : '')
const place = computed(() => props.compact ? roomOf(props.device)?.name : '')
/* A camera brings its own picture, which is rung one and beats any drawing we
   ship -- so this is only for when there is no frame to show: offline, or the
   first seconds before one arrives. Until now that was an empty dark card. */
const shape = computed(() => kindFor('camera', props.device.name) ?? 'camera')
</script>

<template>
  <button class="tile camera wide" :class="{ dead, live, compact }" @click="store.viewer = device" :aria-label="`Open ${device.name} camera`">
    <img v-if="src" :src="src" alt="" />
    <DeviceArt v-if="!src" :kind="shape" :state="{ live }" />
    <div class="camera-veil"></div>
    <div class="camera-top">
      <span class="chip" :class="{ live }">{{ dead ? 'Offline' : live ? 'Recording' : age || 'Loading' }}</span>
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
