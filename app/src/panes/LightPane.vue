<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * A light, opened: the two things a lamp physically is, and the three it is used at.
 *
 * The columns are 168 and 126 wide because the hand that reaches for them is not looking — this is
 * a panel on a wall, and the 4px range input the pane used to carry could only be hit by someone
 * standing in front of it with a mouse. The three cards are for everyone who will never drag
 * anything: each one is a brightness the house can already send.
 */
import { computed } from 'vue'
import type { Device } from '../api'
import { guessNow, isDead, notify, perform } from '../store'
import Icon from '../Icon.vue'
import { useNarrow, useSlide } from './slide'

const props = defineProps<{ device: Device }>()
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const on = computed(() => props.device.state === 'on')
const pct = computed(() => on.value && a.value.brightness != null ? Math.round((a.value.brightness / 255) * 100) : on.value ? 100 : 0)
const dimmable = computed(() => 'brightness' in (a.value ?? {}) || (a.value.supported_color_modes ?? []).some((m: string) => m !== 'onoff'))

/* Warmth only when the lamp has told us a color temperature: a bulb that cannot change its white
   must not be given a column that does nothing. The ends are the ones a domestic bulb actually
   spans, because the brain does not keep this lamp's own limits. */
const WARM = 2000, COOL = 6500
const kelvin = computed(() => a.value.color_temp_kelvin as number | undefined)
const warmth = computed(() => kelvin.value ? Math.round(((kelvin.value - WARM) / (COOL - WARM)) * 100) : null)

async function bright(v: number) {
  const p = Math.max(1, Math.min(100, v))
  if (!await perform(props.device, 'on', { brightness_pct: p }, { state: 'on', attrs: { brightness: Math.round(p * 2.55) } })) return
}
async function warm(v: number) {
  const k = Math.round(WARM + (Math.max(0, Math.min(100, v)) / 100) * (COOL - WARM))
  await perform(props.device, 'on', { color_temp_kelvin: k }, { state: 'on', attrs: { color_temp_kelvin: k } })
}
/* while a finger is down the drawing moves and the house is left alone; see panes/slide.ts */
const guess = computed({
  get: () => pct.value,
  set: (v: number) => guessNow(props.device, { state: on.value ? undefined : 'on', attrs: { brightness: Math.round(v * 2.55) } }),
})
const warmGuess = computed({
  get: () => warmth.value ?? 0,
  set: (v: number) => guessNow(props.device, { attrs: { color_temp_kelvin: Math.round(WARM + (v / 100) * (COOL - WARM)) } }),
})
const narrow = useNarrow()          // a phone drags the same two things on their sides
const dim = useSlide({ vertical: () => !narrow.value, live: v => (guess.value = v), settle: v => bright(v) })
const hue = useSlide({ vertical: () => !narrow.value, live: v => (warmGuess.value = v), settle: v => warm(v) })
const along = (p: number) => narrow.value ? { width: p + '%' } : { height: p + '%' }
const mark = (p: number) => narrow.value ? { left: p + '%' } : { bottom: p + '%' }

/* The three a lamp is actually used at. Fixed for now and deliberately few; what they should
   eventually be is what THIS lamp keeps being set to, which the event log already knows. */
const LEVELS = [
  { id: 'read', name: 'Reading', sub: 'Bright, and cooler', icon: 'sun', pct: 100, k: 4000 },
  { id: 'evening', name: 'Evening', sub: 'Low and warm', icon: 'light', pct: 35, k: 2700 },
  { id: 'night', name: 'Night', sub: 'Enough to see by', icon: 'moon', pct: 5, k: 2200 },
]
const here = computed(() => {
  if (!on.value) return ''
  return LEVELS.reduce((best, l) => Math.abs(l.pct - pct.value) < Math.abs(best.pct - pct.value) ? l : best).id
})
async function level(l: typeof LEVELS[number]) {
  if (dead.value) return
  const data: Record<string, unknown> = dimmable.value ? { brightness_pct: l.pct } : {}
  if (kelvin.value) data.color_temp_kelvin = l.k
  try { await perform(props.device, 'on', data, { state: 'on', attrs: { brightness: Math.round(l.pct * 2.55), ...(kelvin.value ? { color_temp_kelvin: l.k } : {}) } }) }
  catch (e: any) { notify(e.message, 'error') }
}
</script>

<template>
  <div class="rig rig-light">
    <div class="rig-slot" v-if="dimmable">
      <div class="rig-col" role="slider" tabindex="0" :aria-label="`${device.name} brightness`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="pct"
           :class="{ held: dim.held.value, dead, bar: narrow }" @pointerdown="dim.down" @pointermove="dim.move" @pointerup="dim.up" @pointercancel="dim.cancel"
           @keydown="e => dim.key(e, pct)">
        <span class="rig-fill" :style="along(on ? Math.max(pct, 2) : 0)"></span>
        <span class="rig-mark" :style="mark(pct)" v-if="on"></span>
        <span class="rig-end top"><Icon name="sun" :size="21" /></span>
        <span class="rig-end bottom" :class="{ lit: on && pct > 12 }"><Icon name="moon" :size="19" /></span>
      </div>
      <span class="rig-lbl">Brightness</span>
    </div>

    <div class="rig-slot" v-if="warmth != null">
      <div class="rig-col warmth" :class="{ bar: narrow }" role="slider" tabindex="0" :aria-label="`${device.name} warmth`" aria-valuemin="2000" aria-valuemax="6500" :aria-valuenow="kelvin"
           @pointerdown="hue.down" @pointermove="hue.move" @pointerup="hue.up" @pointercancel="hue.cancel" @keydown="e => hue.key(e, warmth ?? 0)">
        <span class="rig-handle" :style="mark(warmth ?? 0)"><i>{{ kelvin }}K</i></span>
      </div>
      <span class="rig-lbl">Warmth</span>
    </div>

    <div class="rig-levels">
      <span class="rig-lbl">The three it is used at</span>
      <button v-for="l in LEVELS" :key="l.id" class="rig-card" :class="{ on: here === l.id }" :disabled="dead" @click="level(l)">
        <span class="rig-card-icon"><Icon :name="l.icon" :size="18" /></span>
        <span class="rig-card-text">
          <span class="rig-card-name">{{ l.name }}</span>
          <span class="rig-card-sub">{{ here === l.id ? 'Where it is now' : l.sub }}</span>
        </span>
      </button>
    </div>
  </div>
</template>
