<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * THE ROOF, AS THE HOUSE KNOWS IT: the floor of the Roofline's own pane (design/roofline/DrawnC.dc.html,
 * chosen 1 October 2026).
 *
 * The lights in the order they go round, each run as long as it is, an arrow over each for the way it
 * leaves its box, and the boxes under it by place, each saying Fine or Dark. So "is the garage end
 * working?" is answered from across the room: a dark stretch is dark where it is, ringed, with what to do
 * under it in the box's own words. Which way round is the door to the yard (YardSheet), where the order is
 * shown on the roof itself; until it has been, each box's runs are drawn apart, because joining them would
 * be a guess drawn as a fact. roof.ts does the arithmetic; this only draws it.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Roofline } from './api'
import { yardBegin } from './api'
import { roofCount, roofMeters } from './controller'
import { calcOf, dotPitch, endOf, roofDots, roofDrawing, roofNext, type Pos, type RoofBoxAt, type RoofItem } from './roof'
import { notify, store } from './store'
import { useNarrow } from './panes/slide'
import Icon from './Icon.vue'

const props = defineProps<{ roof: Extract<Roofline, { exists: true }>; on: boolean }>()
const narrow = useNarrow()

const d = computed(() => roofDrawing(props.roof))
/* One dot for every two lights on a 1440 wall, as the board draws it, and fewer wherever the line is
   shorter -- a phone, or the right-hand column -- because two hundred dots in 300px are a smear rather
   than a string of lights. So the line is measured, not guessed from the screen. */
const line = ref<HTMLElement | null>(null)
const width = ref(0)
let watcher: ResizeObserver | undefined
onMounted(() => {
  if (!line.value || typeof ResizeObserver === 'undefined') return
  watcher = new ResizeObserver(([e]) => { width.value = e.contentRect.width })
  watcher.observe(line.value)
})
onUnmounted(() => watcher?.disconnect())
const pitch = computed(() => width.value ? dotPitch(props.roof.lights, width.value - d.value.fixed) : narrow.value ? 10 : 2)
const dots = computed(() => roofDots(d.value, props.roof, pitch.value, props.on))
const next = computed(() => roofNext(props.roof))
const ring = computed(() => d.value.rings[0] ?? null)
const head = computed(() => d.value.joined ? 'Round the house, left to right' : 'Each strip, from its own controller')
const count = computed(() => `${roofCount(props.roof)} · ${roofMeters(props.roof.lights)}`)
const at = (p: Pos) => calcOf(p, d.value.fixed)
const span = (from: Pos, to: Pos) => ({ left: at(from), width: `calc(${at(to)} - ${at(from)})` })
const place = (it: RoofItem) => span(it.at, endOf(it))
const boxes = computed(() => d.value.items.filter((it): it is RoofBoxAt => it.kind === 'box'))
/* Where the line under the roof goes: under the ring, held to the end it is at -- or, with nothing wrong,
   to the right, where the board puts it. */
const nextAt = computed(() => {
  const r = ring.value
  if (!r) return { right: '0px' }
  return r.align === 'end' ? { right: `calc(100% - ${at(r.to)} + 14px)`, textAlign: 'right' as const }
    : { left: `calc(${at(r.from)} + 14px)`, textAlign: 'left' as const }
})

async function whichWay() {
  try { await yardBegin(); store.yard = true }
  catch (e: any) { notify(e.message, 'error') }
}
</script>

<template>
  <section class="roof-plate" :data-order="d.joined ? 'known' : 'unknown'" aria-label="The roof">
    <div class="roof-plate-head">
      <span class="roof-plate-what"><span class="rig-lbl">{{ head }}</span><span class="roof-plate-count">{{ count }}</span></span>
      <button class="chip-btn roof-way" v-if="roof.runs > 1" @click="whichWay"><Icon name="turn" :size="16" />Which way round</button>
    </div>
    <div class="roof-line" ref="line">
      <span v-for="(g, i) in d.apart" :key="`g${i}`" class="roof-group" :style="span(g.from, g.to)" aria-hidden="true"></span>
      <template v-for="(it, i) in d.items" :key="it.kind === 'run' ? `${it.chip}${it.run}` : `[${it.chip}]`">
        <span v-if="it.kind === 'run'" class="roof-run" :class="{ dark: it.dark }" :style="place(it)" :data-chip="it.chip" :data-run="it.run">
          <span class="roof-arrow" :data-dir="it.dir > 0 ? 'on' : 'back'" aria-hidden="true"><i></i></span>
          <span class="roof-dots" aria-hidden="true">
            <i v-for="(x, k) in dots[i]" :key="k" :class="[x.off ? 'off' : x.motion]"
               :style="{ '--c1': x.c1, '--c2': x.c2, '--dur': `${x.dur}s`, '--delay': `${x.delay.toFixed(3)}s` }"></i>
          </span>
        </span>
        <span v-else class="roof-box" :class="{ dark: it.state !== 'Fine' }" :style="place(it)" :data-chip="it.chip">
          <span class="roof-box-label" :class="it.align" v-if="!narrow">
            <span class="roof-box-place">{{ it.place }}</span>
            <span class="roof-box-state"><i></i>{{ it.state }}</span>
          </span>
        </span>
      </template>
      <span v-for="r in d.rings" :key="r.chip" class="roof-ring" :style="span(r.from, r.to)" aria-hidden="true"></span>
      <p class="roof-said" :class="{ wrong: next.wrong }" :style="nextAt" v-if="!narrow">{{ next.text }}</p>
    </div>
    <!-- a phone: the places in a row under the line, in the order they are along it -->
    <template v-if="narrow">
      <div class="roof-places">
        <span v-for="b in boxes" :key="b.chip" class="roof-box-label" :class="[b.align, { dark: b.state !== 'Fine' }]">
          <span class="roof-box-place">{{ b.place }}</span>
          <span class="roof-box-state"><i></i>{{ b.state }}</span>
        </span>
      </div>
      <p class="roof-said" :class="{ wrong: next.wrong }">{{ next.text }}</p>
    </template>
  </section>
</template>

<style scoped>
/* The board's plate (DrawnC): the width of the pane under both columns, its floor running off the foot
   of the wall the way the pane itself does. Every measure below is the board's, from the plate's corner. */
.roof-plate {
  position: relative;
  min-width: 0;
  min-height: 250px;
  padding: 18px 22px 0 28px;
  border-radius: 32px 32px 0 0;
  border: 1px solid var(--edge);
  border-bottom: 0;
  background: rgba(255, 255, 255, 0.035);
}
.roof-plate-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
}
.roof-plate-what {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 14px;
  min-width: 0;
}
.roof-plate-count {
  font-size: 14px;
  color: var(--muted);
}
.roof-way {
  flex: 0 0 auto;
  height: 40px;
  padding: 0 15px;
  font-size: 14.5px;
  color: var(--ink);
  white-space: nowrap;
  cursor: pointer;
}
/* the line itself: 35 in from either side of the plate, the lights 128 down it */
.roof-line {
  position: absolute;
  left: 35px;
  right: 35px;
  top: 110px;
  height: 36px;
}
.roof-run,
.roof-box,
.roof-ring,
.roof-group {
  position: absolute;
}
.roof-run,
.roof-box {
  top: 12px;
  height: 12px;
}
.roof-dots {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: space-around;
}
.roof-dots i {
  width: 4.4px;
  height: 4.4px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--c1);
  box-shadow: 0 0 6px 1px var(--c1);
}
/* EMITTER COLORS, NOT SCREEN COLORS (AGENTS.md section 4): what the roof is asked for, saturated -- the
   look's own bytes, inline -- never the panel's pastels. A dark run's lights are unlit, not dimmed. */
.roof-dots i.off {
  background: rgba(255, 255, 255, 0.13);
  box-shadow: none;
}
.roof-dots i.chase {
  animation: roof-chase var(--dur) linear var(--delay) infinite;
}
.roof-dots i.flicker {
  animation: roof-flicker var(--dur) ease-in-out var(--delay) infinite;
}
@keyframes roof-chase {
  0%,
  49.9% {
    background: var(--c1);
    box-shadow: 0 0 6px 1px var(--c1);
  }
  50%,
  100% {
    background: var(--c2);
    box-shadow: 0 0 6px 1px var(--c2);
  }
}
@keyframes roof-flicker {
  0%,
  100% {
    opacity: 1;
  }
  40% {
    opacity: 0.45;
  }
  60% {
    opacity: 0.85;
  }
}
@media (prefers-reduced-motion: reduce) {
  .roof-dots i.chase,
  .roof-dots i.flicker {
    animation: none;
  }
}
/* the way a run leaves its box: an arrow over its middle, 38 above the lights */
.roof-arrow {
  position: absolute;
  left: 50%;
  top: -32px;
  width: 40px;
  height: 12px;
  margin-left: -20px;
}
.roof-arrow::before {
  content: '';
  position: absolute;
  left: 2px;
  right: 2px;
  top: 5px;
  height: 1.5px;
  border-radius: 1px;
  background: rgba(255, 255, 255, 0.3);
}
.roof-arrow i {
  position: absolute;
  top: 2px;
  width: 7px;
  height: 7px;
  border: solid rgba(255, 255, 255, 0.3);
  transform: rotate(45deg);
}
.roof-arrow[data-dir='on'] i {
  left: 29px;
  border-width: 1.5px 1.5px 0 0;
}
.roof-arrow[data-dir='back'] i {
  left: 2px;
  border-width: 0 0 1.5px 1.5px;
}
.roof-box {
  border-radius: 3px;
  background: #2e313b;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3);
}
/* the place under the box: the two ends held to the ends, the rest centered on their box */
.roof-box-label {
  position: absolute;
  top: 30px;
  width: 260px;
  display: flex;
  flex-direction: column;
}
.roof-box-label.start {
  left: 0;
  align-items: flex-start;
}
.roof-box-label.center {
  left: 50%;
  margin-left: -130px;
  align-items: center;
}
.roof-box-label.end {
  right: 0;
  align-items: flex-end;
}
.roof-box-place {
  font-size: 17px;
  line-height: 23px;
}
.roof-box-state {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  color: var(--muted);
}
.roof-box-state i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--live);
}
.roof-box.dark .roof-box-state,
.roof-box-label.dark .roof-box-state {
  color: var(--danger);
}
.roof-box.dark .roof-box-state i,
.roof-box-label.dark .roof-box-state i {
  background: var(--danger);
}
.roof-ring {
  top: 0;
  height: 36px;
  border-radius: 18px;
  border: 2px dashed rgba(var(--danger-rgb), 0.9);
  box-shadow: 0 0 0 4px rgba(var(--danger-rgb), 0.1);
  pointer-events: none;
}
.roof-group {
  top: 0;
  height: 36px;
  pointer-events: none;
}
.roof-said {
  position: absolute;
  top: 102px;
  width: max-content;
  max-width: min(520px, 100%);
  margin: 0;
  text-align: right;
  font-size: 15px;
  line-height: 21px;
  color: var(--muted);
}
.roof-said.wrong {
  color: var(--danger);
}

/* A shorter wall: the line moves up under the head, and the plate asks for less of the floor. */
@media (max-height: 860px) and (min-width: 861px) {
  .roof-plate {
    min-height: 196px;
    padding-top: 14px;
  }
  .roof-line {
    top: 88px;
  }
  .roof-said {
    top: 94px;
  }
}

/* A PHONE: the same line across the phone, and the places in a row under it rather than each under its
   box, where three names would print over each other in 300px. */
@media (max-width: 860px) {
  .roof-plate {
    min-height: 0;
    padding: 16px 16px 20px;
    border-radius: 26px;
    border-bottom: 1px solid var(--edge);
  }
  .roof-plate-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .roof-line {
    position: relative;
    left: auto;
    right: auto;
    top: auto;
    height: 36px;
    margin: 40px 4px 0;
  }
  .roof-dots i {
    width: 3.4px;
    height: 3.4px;
  }
  /* a run on a phone is fifty pixels, so its arrow is shorter than a wall's */
  .roof-arrow {
    width: 26px;
    margin-left: -13px;
  }
  .roof-arrow[data-dir='on'] i {
    left: 15px;
  }
  .roof-places {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 8px;
  }
  .roof-places .roof-box-label {
    position: static;
    width: auto;
    min-width: 0;
  }
  .roof-places .roof-box-label.center {
    margin-left: 0;
    text-align: center;
  }
  .roof-places .roof-box-label.end {
    text-align: right;
  }
  .roof-box-place {
    font-size: 15px;
    line-height: 20px;
  }
  .roof-said {
    position: static;
    width: auto;
    max-width: none;
    margin-top: 14px;
    text-align: left;
  }
}
</style>
