<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The house's power, opened in place: design/energy/Pane.dc.html, which every line about power in the band
 * opens, and so does Solar and battery in This house.
 *
 * A device's pane in everything but what is in it, borrowed by class the way PrinterPane borrows it, because
 * the gateway is not a device in a room (brain/hub/power.py). On the left, what the power is doing in a
 * sentence and four facts. On the right, where it is going, as a picture rather than a table of readings.
 * Across the foot, the day so far.
 *
 * How much of the battery is kept for an outage is said, not offered: the gateway lets the house read it and
 * not set it, so the pane says where it is changed.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getPowerDay } from './api'
import { cap, store } from './store'
import { chargerWords, kw } from './chargers'
import { dayPaths, flowWords, flows, powerSentence } from './power'
import Icon from './Icon.vue'

const p = computed(() => store.power)
const shown = ref(false)
const closing = ref(false)
function close() { shown.value = false; closing.value = true; setTimeout(() => (store.powerOpen = false), 320) }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') close() }

async function loadDay() { try { store.powerDay = await getPowerDay() } catch { /* the pane still says what is happening now */ } }
let dayPoll: number | undefined
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))   // two frames: Opened.vue says why
  window.addEventListener('keydown', onKey)
  loadDay(); dayPoll = window.setInterval(loadDay, 300000)
})
onUnmounted(() => { window.removeEventListener('keydown', onKey); clearInterval(dayPoll) })

const sunUp = computed(() => (p.value?.solar ?? 0) >= 0.05)
const big = computed(() => {
  const v = p.value; if (!v) return { n: '', unit: '' }
  if (sunUp.value || v.charge == null) return { n: kw(v.solar ?? 0), unit: 'from the sun' }
  return { n: `${Math.round(v.charge)}%`, unit: 'in the battery' }
})
const sentence = computed(() => p.value ? powerSentence(p.value) : '')
const words = computed(() => p.value ? flowWords(p.value) : null)
const flow = computed(() => p.value ? flows(p.value) : { toHouse: 0, toBattery: 0, toGrid: 0 })
const car = computed(() => store.rooms.flatMap(r => r.devices).find(d => cap(d) === 'charger') ?? null)

const facts = computed(() => {
  const v = p.value, day = store.powerDay
  if (!v) return []
  const out: { k: string; v: string }[] = []
  if (day?.made != null) out.push({ k: 'Made today', v: `${day.made.toFixed(1)} kWh` })
  if (day?.used != null) out.push({ k: 'Used today', v: `${day.used.toFixed(1)} kWh` })
  if (v.charge != null) out.push({ k: 'Battery', v: `${Math.round(v.charge)}%` })
  if (v.grid_up != null) out.push({ k: 'The grid', v: v.grid_up ? 'Up' : 'Out' })
  return out
})

const DAY_W = 1000, DAY_H = 44
const day = computed(() => dayPaths(store.powerDay, DAY_W, DAY_H))
const TICKS = [['6 AM', 0], ['9', 0.2], ['Noon', 0.4], ['3', 0.6], ['6', 0.8], ['9 PM', 1]] as const
</script>

<template>
  <div class="opened power-pane-shell" :class="{ shown, closing }" v-if="p" role="dialog" aria-label="Power">
    <div class="opened-veil" @click="close"></div>
    <div class="opened-panel" data-cap="power">
      <button class="back opened-close" @click="close" aria-label="Close"><Icon name="close" :size="18" /></button>
      <div class="opened-body pane-body">
        <div class="pane-said">
          <div class="opened-step s0">
            <div class="opened-room">Your house</div>
            <h2 class="display opened-name">Power</h2>
          </div>
          <div class="opened-step s2">
            <div class="opened-big display power-big">{{ big.n }}<span class="power-big-unit">{{ big.unit }}</span></div>
            <p class="pane-why" v-if="sentence">{{ sentence }}</p>
          </div>
        </div>
        <div class="opened-step s3 opened-facts pane-facts" v-if="facts.length">
          <div v-for="f in facts" :key="f.k">
            <div class="opened-fact-v">{{ f.v }}</div>
            <div class="opened-fact-k">{{ f.k }}</div>
          </div>
        </div>
        <div class="pane-rig power-rig">
          <div class="power-flow" :class="{ 'has-car': !!car }">
            <svg class="power-lines" viewBox="0 0 700 400" preserveAspectRatio="none" aria-hidden="true">
              <path class="power-line to-house" :class="{ 'power-still': !flow.toHouse }" d="M350 98 L350 166" />
              <path v-if="p.has_battery" class="power-line to-battery" :class="{ 'power-still': !flow.toBattery }" d="M302 52 C 200 52, 110 84, 110 168" />
              <path class="power-line to-grid" :class="{ 'power-still': !flow.toGrid }" d="M398 52 C 500 52, 590 84, 590 168" />
            </svg>
            <span class="power-amount at-house" v-if="flow.toHouse">{{ kw(flow.toHouse) }}</span>
            <span class="power-amount at-battery" v-if="flow.toBattery && p.has_battery">{{ kw(flow.toBattery) }}</span>
            <span class="power-amount at-grid" v-if="flow.toGrid">{{ kw(flow.toGrid) }}</span>
            <div class="power-node power-sun" :class="{ up: sunUp }"><span class="power-orb"><Icon name="sun" :size="30" /></span><b class="power-narrow">The sun</b><small class="power-narrow">{{ words?.sun }}</small></div>
            <div class="power-node power-house"><span class="power-orb"><Icon name="home" :size="26" /></span><b>The house</b><small>{{ words?.house }}</small></div>
            <div class="power-node power-battery" v-if="p.has_battery"><span class="power-orb" :style="{ '--charge': `${p.charge ?? 0}%` }"><Icon name="battery" :size="26" /></span><b>Battery</b><small>{{ words?.battery }}</small></div>
            <div class="power-node power-grid" :class="{ out: p.grid_up === false }"><span class="power-orb"><Icon name="grid" :size="26" /></span><b>The grid</b><small>{{ words?.grid }}</small></div>
            <div class="power-node power-car" v-if="car"><span class="power-orb"><Icon name="charger" :size="22" /></span><b>The car</b><small>{{ chargerWords(car) }}</small></div>
          </div>
          <p class="power-reserve" v-if="p.reserve != null"><span class="opened-fact-k">Kept for an outage</span><span><b>{{ Math.round(p.reserve) }}%</b> · changed in the Tesla app</span></p>
        </div>
      </div>
      <div class="opened-step s3 pane-day power-day" v-if="day.sun || day.house">
        <span class="opened-fact-k pane-day-head">Today</span>
        <div class="power-day-chart">
          <svg :viewBox="`0 0 ${DAY_W} ${DAY_H}`" preserveAspectRatio="none" aria-hidden="true">
            <path class="power-day-sun" :d="day.sun" />
            <path class="power-day-house" :d="day.house" />
            <line v-if="day.now != null" class="power-day-now" :x1="day.now" :x2="day.now" y1="0" :y2="DAY_H" />
          </svg>
          <div class="power-day-ticks"><span v-for="[t, at] in TICKS" :key="t" :style="{ left: `${at * 100}%` }">{{ t }}</span></div>
        </div>
      </div>
    </div>
  </div>
</template>
