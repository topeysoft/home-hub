<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Device } from '../api'
import { perform, shortName, roomOf, store, isDead } from '../store'
import Icon from '../Icon.vue'
import DeviceArt from '../DeviceArt.vue'
import { lightKind } from '../art'
import { leadsFixture, partnerOf, seeing, speedWord } from '../units'

const props = defineProps<{ device: Device }>()
const on = computed(() => props.device.state === 'on')
const dead = computed(() => isDead(props.device))
const pending = computed(() => !!store.pending[props.device.id])
const dimmable = computed(() => !!(props.device.attrs.supported_color_modes ?? []).some((m: string) => m !== 'onoff'))
const live = computed(() => Math.round((props.device.attrs.brightness ?? 0) / 2.55))
const preview = ref<number | null>(null)
const pct = computed(() => preview.value ?? (on.value ? live.value || 100 : 0))
const name = computed(() => shortName(props.device, roomOf(props.device)))
/* Which drawing this light gets. A guess off the name for now -- see lightKind's
   own note; the real answer is a per-device setting nobody has been asked for yet. */
const kind = computed(() => lightKind(props.device.name || name.value))
/* What it is doing, in the words the boards use: on, and how much of itself it
   is giving. The tile used to say "35% · slide to dim" until the first drag --
   a number with an instruction stapled to it, in lamplight, on the one line a
   person reads from the far side of the room. The gesture is still here and the
   pane still says it in a sentence; the tile says the state. */
/* A light with a motion sensor built in (units.ts) says so here, on the one line, while it sees
   someone: the sensor is part of the same thing on the wall, and this tile is where the thing is. */
const eye = computed(() => seeing(props.device))
/* a fan with a light in it, when the owner has said the light is the tile: the fan is a row on it (units.ts).
   The row stops the pointer, because the tile around it is the dimmer and a tap on the fan is not a tap
   on the light. */
const carried = computed(() => leadsFixture(props.device) ? partnerOf(props.device) : undefined)
function tapCarried() {
  const c = carried.value; if (!c || isDead(c)) return
  perform(c, c.state === 'on' ? 'off' : 'on', undefined, { state: c.state === 'on' ? 'off' : 'on' })
}
const label = computed(() => {
  if (dead.value) return 'Not responding'
  const base = !on.value ? 'Off' : !dimmable.value ? 'On' : `On, ${pct.value}%`
  return eye.value ? `${base} · Motion` : base
})

let startX = 0, dragging = false, el: HTMLElement | null = null
function down(e: PointerEvent) {
  if (dead.value) return
  el = e.currentTarget as HTMLElement; el.setPointerCapture(e.pointerId); startX = e.clientX; dragging = false
}
function move(e: PointerEvent) {
  if (!el || !dimmable.value) return
  if (!dragging && Math.abs(e.clientX - startX) > 8) dragging = true
  if (dragging) {
    const r = el.getBoundingClientRect()
    preview.value = Math.min(100, Math.max(1, Math.round(((e.clientX - r.left) / r.width) * 100)))
  }
}
/* The hold that opens a card swallows the release so a light never toggles on its way into its own panel
   (hold.ts says why). The cost is that this tile is never told the pointer has gone, and a tile that still
   believes a finger is down goes on dimming to a mouse that is only passing over it. Losing the capture is
   the one signal that arrives either way, and it ends the gesture without doing anything -- a hold asked to
   open the panel, it did not ask for a new brightness. A cancelled pointer means the same thing: the gesture
   stopped, so nothing was asked for. */
function release() { el = null; dragging = false; preview.value = null }

async function up() {
  if (!el) return
  el = null
  const d = props.device
  if (dragging && preview.value != null) {
    await perform(d, 'on', { brightness_pct: preview.value }, { state: 'on', attrs: { brightness: Math.round(preview.value * 2.55) } })
  } else {
    await perform(d, on.value ? 'off' : 'on', undefined, { state: on.value ? 'off' : 'on' })
  }
  preview.value = null
}
</script>

<template>
  <div class="tile light" :class="{ on, dead, dimmable, pending, seeing: eye }" role="button" :aria-label="`${name}, ${label}`" :aria-pressed="on"
       tabindex="0" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="release" @lostpointercapture="release" @keydown.enter.space.prevent="perform(device, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' })">
    <div class="fill" :style="{ width: pct + '%' }"></div>
    <DeviceArt :kind="kind" :state="{ on, brightness: pct / 100 }" />
    <span class="tile-maker" v-if="device.maker">{{ device.maker }}</span>
    <div class="tile-body">
      <span class="tile-icon"><Icon name="light" /></span>
      <span class="tile-name">{{ name }}</span>
      <span class="tile-state">{{ label }}</span>
      <span class="machine-rows tile-carry" v-if="carried">
        <span class="machine-row" role="button" tabindex="0" :class="{ on: carried.state === 'on', dead: isDead(carried), pending: !!store.pending[carried.id] }"
              :aria-pressed="carried.state === 'on'" :title="`Hold to open ${carried.name}`"
              @click.stop="tapCarried" @pointerdown.stop @pointermove.stop @pointerup.stop @keydown.enter.space.prevent.stop="tapCarried" v-hold="() => (store.opened = carried!)">
          <Icon name="fan" :size="15" /><span class="machine-row-name">Fan</span><span class="machine-row-state">{{ isDead(carried) ? 'Not responding' : speedWord(carried) }}</span>
        </span>
      </span>
    </div>
  </div>
</template>
