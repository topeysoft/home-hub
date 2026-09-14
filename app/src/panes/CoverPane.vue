<script setup lang="ts">
/*
 * A blind, where the blind IS the control: drag its edge to where you want it, against the sky the
 * panel is already painting behind everything else.
 *
 * A cover that reports no position — most garage doors — has nothing to drag, so it gets the two
 * buttons at full width instead of a picture that cannot move. That fallback is the whole reason
 * this pane asks `current_position` rather than the capability.
 */
import { computed } from 'vue'
import type { Device } from '../api'
import { isDead, perform } from '../store'
import Icon from '../Icon.vue'
import { useSlide } from './slide'

const props = defineProps<{ device: Device }>()
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const positioned = computed(() => a.value.current_position != null)
const open = computed(() => positioned.value ? Number(a.value.current_position) : props.device.state === 'open' ? 100 : 0)
const moving = computed(() => props.device.state === 'opening' || props.device.state === 'closing')

const to = (p: number) => perform(props.device, 'set', { position: Math.round(p) }, { attrs: { current_position: Math.round(p) }, state: p > 0 ? 'open' : 'closed' })
const slide = useSlide({
  live: v => (props.device.attrs = { ...a.value, current_position: v }),
  settle: v => { to(v) },
})
</script>

<template>
  <div class="rig rig-cover">
    <template v-if="positioned">
      <div class="rig-window" role="slider" tabindex="0" :aria-label="`${device.name}, how far open`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="open"
           @pointerdown="slide.down" @pointermove="slide.move" @pointerup="slide.up" @pointercancel="slide.cancel" @keydown="e => slide.key(e, open)">
        <span class="rig-window-sky"></span>
        <span class="rig-blind" :style="{ height: (100 - open) + '%' }">
          <span class="rig-blind-grip"><i></i></span>
        </span>
      </div>
      <div class="rig-scale" aria-hidden="true">
        <span class="rig-scale-line"></span>
        <span class="rig-scale-top">Wide open</span>
        <span class="rig-scale-now" :style="{ bottom: open + '%' }"><i></i>{{ open }}%</span>
        <span class="rig-scale-bottom">Shut</span>
      </div>
    </template>

    <div class="rig-cover-acts" :class="{ wide: !positioned }">
      <button class="rig-btn" :disabled="dead" @click="perform(device, 'open', undefined, { state: 'opening' })">
        <Icon name="plus" :size="20" /><span>Right up</span>
      </button>
      <button class="rig-btn" :disabled="dead || !moving && !positioned" @click="perform(device, 'stop')">
        <Icon name="close" :size="20" /><span>Stop there</span>
      </button>
      <button class="rig-btn" :disabled="dead" @click="perform(device, 'close', undefined, { state: 'closing' })">
        <Icon name="minus" :size="20" /><span>Right down</span>
      </button>
    </div>
  </div>
</template>
