<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The one control in the house that is not a tap.
 *
 * Everything else here opens on a touch, and that is right for a lamp. A front door is different:
 * a sleeve brushing a wall panel must never unlock it, and somebody standing in front of it must
 * be able to see that it did not. So the track is carried the whole way or nothing happens, and
 * what was on the screen stays exactly where it was.
 *
 * The old pane offered this door a power button, which sent act(id, 'on') — an action the brain
 * has no entry for, so the house answered 400 and threw an error across the screen.
 */
import { computed, ref } from 'vue'
import type { Device } from '../api'
import { isDead, perform, store } from '../store'
import Icon from '../Icon.vue'
import { useSlide } from './slide'

const props = defineProps<{ device: Device }>()
const dead = computed(() => isDead(props.device))
const locked = computed(() => props.device.state === 'locked')
const busy = computed(() => props.device.state === 'locking' || props.device.state === 'unlocking' || !!store.pending[props.device.id])

/* How far along the track the knob is while a finger is on it. 0 at rest; nothing happens below
   the whole way, and letting go early puts it back where it was. */
const at = ref(0)
const DONE = 88
const slide = useSlide({
  vertical: false,
  live: v => (at.value = v),
  settle: v => {
    at.value = 0
    if (v < DONE || dead.value) return
    locked.value
      ? perform(props.device, 'unlock', undefined, { state: 'unlocked' })
      : perform(props.device, 'lock', undefined, { state: 'locked' })
  },
})

/* a camera in the same room is the other half of answering the door */
const doorCam = computed(() => store.rooms.find(r => r.id === props.device.room_id)?.devices.find(d => d.capability === 'camera'))
</script>

<template>
  <div class="rig rig-lock">
    <div class="rig-door" :class="{ locked }" aria-hidden="true">
      <span class="rig-door-panel top"></span>
      <span class="rig-door-panel bottom"></span>
      <span class="rig-door-knob"></span>
      <span class="rig-jamb"></span>
      <span class="rig-bolt"></span>
    </div>

    <div class="rig-lock-side">
      <span class="rig-lbl">{{ locked ? 'To open it' : 'To lock it' }}</span>
      <div class="rig-track" :class="{ dead, busy }" role="slider" tabindex="0"
           :aria-label="locked ? `Slide to unlock ${device.name}` : `Slide to lock ${device.name}`"
           aria-valuemin="0" aria-valuemax="100" :aria-valuenow="at"
           @pointerdown="slide.down" @pointermove="slide.move" @pointerup="slide.up" @pointercancel="slide.cancel"
           @keydown="e => slide.key(e, at)">
        <span class="rig-track-fill" :style="{ width: Math.max(at, 0) + '%' }"></span>
        <span class="rig-track-knob" :class="{ open: !locked }" :style="{ left: at + '%' }"><Icon :name="locked ? 'lock' : 'unlock'" :size="30" /></span>
        <span class="rig-track-words">{{ busy ? 'Just a moment…' : locked ? 'Slide to unlock' : 'Slide to lock' }}</span>
      </div>
      <p class="rig-note">{{ locked ? 'It stays locked until somebody carries this the whole way.' : 'Left unlocked. A routine can lock it again at bedtime.' }}</p>

      <div class="rig-lock-acts" v-if="doorCam">
        <button class="rig-btn" @click="store.viewer = doorCam!; store.opened = null">
          <Icon name="camera" :size="20" /><span>See who is there</span>
        </button>
      </div>
    </div>
  </div>
</template>
