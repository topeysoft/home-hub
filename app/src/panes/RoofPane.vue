<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The Roofline, opened: the right-hand side of its own pane (design/roofline/DrawnC.dc.html, chosen
 * 1 October 2026). The roof itself is drawn across the floor of the pane, under this (RoofPlate.vue).
 *
 * What a lamp's pane has and a roof does not use is not here: no Automatic, no colors and More colors --
 * the season decides a roof's colors, and a look of the household's own is said in the command box -- and
 * no Reading, Evening or Night, because nobody reads by a roof. What is left is brightness, laid along the
 * top as the bar a phone already draws every light's brightness as, so the look and its evenings can sit
 * side by side under it: the look with Moving or Hold it still, the one control over how an occasion
 * looks, and Say another look, which is the command box; and its evenings, like a porch light.
 */
import { computed, ref } from 'vue'
import type { Device, Evenings } from '../api'
import { holdStill, setEvenings } from '../api'
import { guessNow, isDead, loadRoofline, notify, perform, store } from '../store'
import { evenOf, lookDates } from '../roof'
import Icon from '../Icon.vue'
import { useSlide } from './slide'

const props = defineProps<{ device: Device }>()
const emit = defineEmits<{ close: [] }>()
const roof = computed(() => (store.roofline?.exists ? store.roofline : null))
const dead = computed(() => isDead(props.device))
const on = computed(() => props.device.state === 'on')
const a = computed(() => props.device.attrs)
const pct = computed(() => on.value && a.value.brightness != null ? Math.round((a.value.brightness / 255) * 100) : on.value ? 100 : 0)

/* Brightness, the same target as every light's and the same gesture: the drawing moves under the finger
   and the house is told on the way up (panes/slide.ts). Only its shape is a phone's, on its side. */
async function bright(v: number) {
  const p = Math.max(1, Math.min(100, v))
  await perform(props.device, 'on', { brightness_pct: p }, { state: 'on', attrs: { brightness: Math.round(p * 2.55) } })
}
const guess = computed({
  get: () => pct.value,
  set: (v: number) => guessNow(props.device, { state: on.value ? undefined : 'on', attrs: { brightness: Math.round(v * 2.55) } }),
})
const dim = useSlide({ vertical: false, live: v => (guess.value = v), settle: v => bright(v) })

const EVENING_CHOICES: { id: Evenings; name: string }[] = [
  { id: 'every', name: 'Every evening' }, { id: 'occasion', name: 'Only for occasions' }, { id: 'never', name: 'Not by itself' },
]
const busy = ref('')
async function act(id: string, fn: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = id
  try { await fn(); await loadRoofline() } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
const evenings = (m: Evenings) => act(m, () => setEvenings(m))
const still = (v: boolean) => act(v ? 'still' : 'moving', () => holdStill(v))
const even = computed(() => roof.value ? evenOf(roof.value) : null)
const dates = computed(() => roof.value ? lookDates(roof.value) : '')

/* SAY ANOTHER LOOK. A look is said, not picked (design/roofline/SaidC.dc.html): the pane gets out of the
   way and the command box opens with the occasion already said, so what is typed next is the look. */
function sayAnother() {
  const name = roof.value?.occasion_name
  store.sayStart = name ? `${name}: ` : ''
  emit('close')
}
</script>

<template>
  <div class="roof-rig" v-if="roof">
    <div class="rig-col bar roof-bar" role="slider" tabindex="0" :aria-label="`${device.name} brightness`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="pct"
         :class="{ held: dim.held.value, dead }" @pointerdown="dim.down" @pointermove="dim.move" @pointerup="dim.up" @pointercancel="dim.cancel"
         @keydown="e => dim.key(e, pct)">
      <span class="rig-fill" :style="{ width: (on ? Math.max(pct, 2) : 0) + '%' }"></span>
      <span class="rig-mark" :style="{ left: pct + '%' }" v-if="on"></span>
      <span class="rig-end bottom" :class="{ lit: on && pct > 8 }"><Icon name="moon" :size="19" /></span>
      <span class="roof-bar-lbl" :class="{ lit: on && pct > 18 }">Brightness</span>
      <span class="rig-end top" :class="{ lit: on && pct > 94 }"><Icon name="sun" :size="21" /></span>
    </div>

    <div class="roof-cards">
      <div class="roof-card roof-look">
        <div class="roof-card-head">
          <span class="roof-card-name">{{ roof.occasion_name ?? 'Its everyday light' }}</span>
          <span class="roof-card-when" v-if="dates">{{ dates }}</span>
        </div>
        <span class="roof-card-sub">{{ roof.words ?? 'Warm white. No occasion, no colors.' }}</span>
        <div class="roof-card-foot">
          <div class="roof-chips" v-if="roof.occasion">
            <button class="chip-btn" :class="{ on: !roof.still, busy: busy === 'moving' }" :aria-pressed="!roof.still" @click="still(false)">Moving</button>
            <button class="chip-btn" :class="{ on: roof.still, busy: busy === 'still' }" :aria-pressed="roof.still" @click="still(true)">Hold it still</button>
          </div>
          <button class="roof-say" @click="sayAnother">Say another look</button>
        </div>
      </div>

      <div class="roof-card roof-evenings" v-if="even">
        <span class="roof-card-name">{{ even.name }}</span>
        <span class="roof-card-sub">{{ even.sub }}</span>
        <div class="roof-card-foot">
          <div class="roof-chips">
            <button class="chip-btn" v-for="e in EVENING_CHOICES" :key="e.id" :class="{ on: roof.evenings === e.id, busy: busy === e.id }"
                    :aria-pressed="roof.evenings === e.id" @click="evenings(e.id)">{{ e.name }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The board's measures (DrawnC): a 72px bar, then 20 down, two cards 200 high with 14 between them. */
.roof-rig {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
/* the panel's own bar -- the column a phone turns on its side -- at the width of the controls */
.rig-col.roof-bar {
  flex: 0 0 auto;
  width: 100%;
  height: 72px;
  min-height: 0;
  border-radius: 36px;
}
/* the fill is the light's own color, as the column is on every pane; the phone's bar is drawn amber */
.rig-col.roof-bar .rig-fill {
  background: linear-gradient(
    90deg,
    color-mix(in oklab, rgb(var(--lamp-rgb)) 82%, #000000),
    color-mix(in oklab, rgb(var(--lamp-rgb)) 62%, #ffffff)
  );
}
.rig-col.roof-bar .rig-mark {
  top: 18px;
  bottom: 18px;
}
.rig-col.roof-bar .rig-end.bottom {
  left: 18px;
}
.rig-col.roof-bar .rig-end.top {
  right: 26px;
}
.rig-col.roof-bar .rig-end.top.lit {
  color: rgba(var(--lamp-ink-rgb), 0.5);
}
.roof-bar-lbl {
  position: absolute;
  left: 66px;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  font-size: 12.5px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  pointer-events: none;
}
.roof-bar-lbl.lit {
  color: rgba(var(--lamp-ink-rgb), 0.62);
}
.roof-cards {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}
.roof-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 200px;
  padding: 20px 22px;
  border-radius: 24px;
  border: 1px solid var(--edge);
  background: rgba(var(--wash-rgb), 0.05);
}
.roof-card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}
.roof-card-name {
  display: block;
  font-size: 19px;
  line-height: 26.6px;
}
.roof-card-when {
  flex: 0 0 auto;
  font-size: 14px;
  color: var(--muted);
}
.roof-look .roof-card-sub {
  margin-top: 2px;
  font-size: 15px;
  line-height: 21px;
  color: var(--ink-2);
}
.roof-card-sub {
  display: block;
  margin-top: 2px;
  font-size: 14px;
  line-height: 19.6px;
  color: var(--muted);
}
/* the chips sit at the foot of the card, as the board draws them, however much is said above */
.roof-card-foot {
  margin-top: auto;
  padding-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
}
.roof-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.roof-chips .chip-btn {
  height: 40px;
  padding: 0 15px;
  font-size: 14.5px;
  white-space: nowrap;
  cursor: pointer;
}
.roof-chips .chip-btn:not(.on) {
  color: var(--ink);
}
.roof-say {
  padding: 0 0 2px;
  border: 0;
  border-bottom: 1px solid rgba(var(--wash-rgb), 0.18);
  background: none;
  color: var(--ink-2);
  font: inherit;
  font-size: 14.5px;
  white-space: nowrap;
  cursor: pointer;
}
.roof-say:hover {
  color: var(--ink);
}
/* A SHORTER WALL (1280x800). The board is drawn at 1440x900; on a wall a hundred pixels shorter the bar,
   the cards and their chips give up a little height each so the roof still fits under them and nothing
   scrolls. Same arrangement, tighter. */
@media (max-height: 860px) and (min-width: 861px) {
  .roof-rig {
    gap: 14px;
  }
  .rig-col.roof-bar {
    height: 60px;
    border-radius: 30px;
  }
  .rig-col.roof-bar .rig-mark {
    top: 14px;
    bottom: 14px;
  }
  .roof-card {
    min-height: 0;
    padding: 16px 18px;
  }
  .roof-card-foot {
    padding-top: 10px;
    gap: 6px 10px;
  }
  .roof-chips {
    gap: 6px;
  }
  .roof-chips .chip-btn {
    height: 34px;
    padding: 0 12px;
    font-size: 14px;
  }
}
/* a phone: the two cards one above the other, under the bar */
@media (max-width: 860px) {
  .roof-cards {
    grid-template-columns: minmax(0, 1fr);
  }
  .roof-card {
    min-height: 0;
  }
}
</style>
