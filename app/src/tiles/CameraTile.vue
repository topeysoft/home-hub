<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
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

<style scoped>
/* CameraTile's own insides. Every rule here matches something this template draws, so `scoped`
   narrows it to the elements it already applied to, and these names can no longer collide with
   another screen's by accident.

   What stayed in panel.css, deliberately: anything on the component's outermost element, because
   that is where the rest of the sheet does its cross-cutting work and scoping would make a moved
   rule outrank the ones it used to tie with; any class another component also draws, which is
   shared vocabulary rather than ours; and any rule reaching in from a container (`.bento`,
   `.wall-stage`), which belongs to the arrangement rather than to this. */

.camera-veil {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgba(12, 13, 16, 0.35),
    transparent 35%,
    transparent 55%,
    rgba(12, 13, 16, 0.8)
  );
}
.camera-top {
  position: absolute;
  top: 14px;
  right: 14px;
}
.chip {
  font-size: 11.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(12, 13, 16, 0.55);
  color: var(--ink-2);
  backdrop-filter: blur(8px);
}
.chip.live {
  background: var(--live);
  color: #0b2216;
  font-weight: 600;
}
.camera-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.camera-place {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.7);
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.5);
}</style>
