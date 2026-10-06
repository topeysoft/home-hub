<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Motion, a thermometer, a door contact: the three kinds with no verb at all.
 *
 * They were also the three that could not be opened, because the room screen gives them a reading
 * in its header rather than a tile and there was nothing to press and hold. That is now what the
 * reading itself does — and this is what it opens, which is the only thing a watcher has to give:
 * the day it has had. Both shapes come from the event log, which has always kept them.
 */
import { computed } from 'vue'
import type { Device, Event } from '../api'
import { cap, store } from '../store'
import { spans, trace } from '../pane'
import { readingLabel } from '../readings'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device; events: Event[] }>()
const kind = computed(() => cap(props.device))
const numeric = computed(() => kind.value === 'sensor')
const unit = computed(() => {
  const cls = props.device.capability.split('.')[1]
  return cls === 'temperature' ? (store.tempUnit || '°').replace(/[^°CF]/g, '') : cls === 'humidity' ? '%' : cls === 'illuminance' ? ' lx' : ''
})

const bars = computed(() => spans(props.events))
const line = computed(() => {
  const t = trace(props.events)
  if (t.pts.length < 2) return null
  const pad = Math.max(1, (t.high - t.low) * 0.15)
  const lo = t.low - pad, hi = t.high + pad
  const y = (v: number) => 100 - ((v - lo) / (hi - lo)) * 100
  const d = t.pts.map((p, i) => `${i ? 'L' : 'M'}${(p.x * 100).toFixed(2)} ${y(p.y).toFixed(2)}`).join(' ')
  return { d, fill: `${d} L100 100 L0 100 Z`, low: t.low, high: t.high }
})
/* how much of the day it was on, which is the number a strip is read for */
const forToday = computed(() => {
  const mins = bars.value.reduce((s, b) => s + (b.to - b.from), 0) * ((Date.now() - new Date().setHours(0, 0, 0, 0)) / 60000)
  return mins < 1 ? 'under a minute' : mins < 60 ? `${Math.round(mins)} min` : `${Math.round(mins / 60)} h`
})
const times = computed(() => props.events.filter(e => e.kind === 'state' && e.new === 'on').length)
</script>

<template>
  <div class="rig rig-sense">
    <div class="rig-sense-head">
      <span class="rig-lbl">Today</span>
      <span class="rig-sense-now" :class="{ on: device.state === 'on' }"><Icon :name="kind" :size="18" />{{ readingLabel(device) }}</span>
    </div>

    <!-- a thermometer: the day as a line, with what it has been between -->
    <div class="rig-graph" v-if="numeric">
      <svg v-if="line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path :d="line.fill" class="rig-graph-fill" />
        <path :d="line.d" class="rig-graph-line" vector-effect="non-scaling-stroke" />
      </svg>
      <p class="rig-empty" v-else>Nothing written down yet today. The house keeps a reading each time this one changes.</p>
      <div class="rig-graph-ends" v-if="line">
        <span>Low {{ Math.round(line.low) }}{{ unit }}</span>
        <span>High {{ Math.round(line.high) }}{{ unit }}</span>
        <span>Now {{ readingLabel(device) }}</span>
      </div>
    </div>

    <!-- motion, or a door: the day as a strip of when it was on -->
    <div class="rig-strip-wrap" v-else>
      <div class="rig-strip" :class="kind">
        <span v-for="(b, i) in bars" :key="i" class="rig-blip"
              :style="{ left: (b.from * 100) + '%', width: Math.max(0.6, (b.to - b.from) * 100) + '%' }"></span>
      </div>
      <div class="rig-strip-ends"><span>Midnight</span><span>Noon</span><span>Now</span></div>
      <p class="rig-empty" v-if="!bars.length">Nothing since midnight.</p>
      <div class="rig-strip-sum" v-else>
        <span><b>{{ times }}</b> {{ kind === 'motion' ? (times === 1 ? 'time' : 'times') : (times === 1 ? 'opening' : 'openings') }}</span>
        <span><b>{{ forToday }}</b> {{ kind === 'motion' ? 'of movement' : 'open' }}</span>
      </div>
    </div>
  </div>
</template>
