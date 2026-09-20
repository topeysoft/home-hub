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
import { bulbColor, lightKind } from '../art'
import { oklch } from '../sky'
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
/* What color this bulb says it is, if it can say. The card wears it as well as
   the drawing: a lamp's light is what fills its card, which is the whole reason
   a lit light reads across a room while a thermostat's state did not, and a
   magenta bulb drawn on an amber card would be saying two things at once. Off
   bulbs wear nothing -- an unlit lamp has no color to show. */
const color = computed(() => (on.value ? bulbColor(props.device.attrs) : undefined))
const wash = computed(() => {
  const c = color.value
  if (!c) return undefined
  const rgb = c.join(',')
  /* The card a lit light gets, in the bulb's own hue instead of the tone's.

     Not a wash over it: the same card toneVars builds, at the same distance from
     the sky and the same chroma, turned to a different place on the wheel. That
     matters because --card-light IS the card on the glass face -- the rule there
     is `background-image: var(--glass-sweep), var(--card-light, ...)`, so a lit
     light is not a frosted pane at all, it is the tone's warm card with the
     sweep laid over it. Leave that alone and a pink bulb sits on an amber card,
     which is the two-things-at-once this is here to stop. Replace it with a wash
     over --card-plain, as the first pass did, and the card stops being a card:
     at noon that came out as the milky pink rectangle this replaced.

     Built from --card-l and --card-c, which toneVars already publishes, so the
     lightness and the chroma stay whatever the hour and the tone say they are
     and only the hue is the bulb's. The card still lightens through the morning
     with every other card, and --card-ink still flips at the right moment,
     because none of the numbers that decide those has moved. */
  const H = oklch(c).H
  return {
    '--card-light': `linear-gradient(155deg, oklch(calc(var(--card-l) + .055) var(--card-c) ${H.toFixed(1)}),`
      + ` oklch(var(--card-l) var(--card-c) ${(H + 6).toFixed(1)}))`,
    /* Both forms, and they are not interchangeable: the dimmer's fill and the
       lit card's border are written against `--lamp-rgb` (bare channels, for
       rgba()) while the bar across the foot uses `--lamp`. Setting only one
       leaves a pink lamp with an amber wash behind it, which is the two-things-
       at-once this is meant to stop.

       And these two are the WHOLE of it. The first pass also repainted the card
       itself, by handing --card-light a wash over --card-plain -- which on the
       glass face quietly swapped the frosted pane for a plain card, so a lit
       Hue came out as a milky pink rectangle with the drawing barely in it. The
       board never did that: its card is the pane, unchanged, and the color
       arrives as LIGHT in it -- the cone out of the fitting, the pool it lands
       in, the dimmer's own wash, the bar and the badge. */
    '--lamp': `rgb(${rgb})`,
    '--lamp-rgb': rgb,
    /* and the state line, which has its own token because it has to read as
       lamplight against a card that may have gone pale by noon -- toneVars sets
       it to #e9b872 or #7a4a10 depending. Both are amber, which was right while
       every lamp was, and is the last thing on this card still saying a color
       the bulb is not. Same two answers, at the bulb's hue: the lit card's own
       lightness decides which, so it is the card that flips it, not the sky. */
    '--card-lamp-ink': `oklch(calc(.82 - var(--card-flip, 0) * .42) .16 ${H.toFixed(1)})`,
  }
})
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
   open the panel, it did not ask for a new brightness. A canceled pointer means the same thing: the gesture
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
  <div class="tile light" :class="{ on, dead, dimmable, pending, seeing: eye }" :style="wash" role="button" :aria-label="`${name}, ${label}`" :aria-pressed="on"
       tabindex="0" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="release" @lostpointercapture="release" @keydown.enter.space.prevent="perform(device, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' })">
    <div class="fill" :style="{ width: pct + '%' }"></div>
    <DeviceArt :kind="kind" :state="{ on, brightness: pct / 100, color }" />
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
