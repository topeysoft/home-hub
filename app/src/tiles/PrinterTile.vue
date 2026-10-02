<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * A printer in its room: design/printers/InRoomA's tile, which B uses wherever a household has chosen a
 * room for one (WorkshopB). A printer is a thing in the room, beside the bench light and the door.
 *
 * Printing is a way of being on, so a printer with a print is a whole column: its camera across the top,
 * and how far and when it will be done. A printer that stopped turns the fault color and says the
 * printer's own sentence, and since when. A ready one is a plain small tile that says Ready, and what it
 * has loaded. A tap opens its pane; nothing on the tile does anything to the printer, for the same reason
 * the print card on Your afternoon has no buttons.
 */
import { computed, ref } from 'vue'
import type { Printer } from '../api'
import { apiUrl } from '../door'
import { clockNow, store } from '../store'
import { doneAt, finishedLine, hasCard, layerLine, percent, timeLeft } from '../printers'
import { locale } from '../lang'
import Icon from '../Icon.vue'

const props = defineProps<{ printer: Printer }>()
const p = computed(() => props.printer)
const tall = computed(() => hasCard(p.value))
const fault = computed(() => p.value.state === 'problem')
const pct = computed(() => percent(p.value))
const word = computed(() => (p.value.word || '').replace(/^./, c => c.toUpperCase()))
const since = computed(() => p.value.since ? `since ${new Date(p.value.since * 1000).toLocaleTimeString(locale(), { hour: 'numeric', minute: '2-digit' })}` : '')
const camOk = ref(true)
const open = () => (store.printer = p.value.id)
</script>

<template>
  <button class="tile printer-tile" :class="{ tall, fault, ready: !tall && !fault }" :aria-label="`${p.name}: ${p.headline}`" @click="open">
    <template v-if="tall">
      <div class="printer-tile-cam">
        <img v-if="camOk" :src="apiUrl(p.camera)" alt="" @error="camOk = false" />
        <span class="print-chip" :class="{ waiting: p.state === 'needs_you', fault }"><i></i>{{ p.state === 'needs_you' ? 'Waiting for you' : p.state === 'finished' ? 'Done' : fault ? 'Stopped' : 'Live' }}</span>
      </div>
      <div class="printer-tile-body">
        <div class="printer-tile-head"><Icon name="printer" :size="18" /><span class="printer-tile-name">{{ p.name }}</span><span class="printer-tile-word">{{ word }}</span></div>
        <div class="printer-tile-job">{{ [p.job?.name, p.job?.filament].filter(Boolean).join(' · ') }}</div>
        <template v-if="p.state === 'printing' || p.state === 'preparing'">
          <div class="print-how">
            <span class="print-pct display">{{ pct ?? 0 }}%</span>
            <span class="print-when" v-if="p.job?.remaining_s != null || p.job?.eta_clock">Done at<b>{{ doneAt(p, clockNow(), locale()) }}</b></span>
          </div>
          <div class="print-bar"><i :style="{ width: `${pct ?? 0}%` }"></i></div>
          <div class="print-foot"><span>{{ layerLine(p) }}</span><span>{{ timeLeft(p) }}</span></div>
        </template>
        <template v-else>
          <h3 class="print-says display">{{ p.headline }}</h3>
          <p class="print-detail" v-if="p.detail">{{ p.detail }}</p>
          <p class="print-finished" v-if="p.state === 'finished' && finishedLine(p, locale())"><Icon name="check" :size="16" />{{ finishedLine(p, locale()) }}</p>
        </template>
      </div>
    </template>

    <template v-else-if="fault">
      <div class="printer-tile-head"><span class="printer-tile-badge"><Icon name="printer" :size="18" /></span><span class="printer-tile-name">{{ p.name }}</span></div>
      <h3 class="printer-tile-says display">{{ p.headline }}</h3>
      <p class="print-detail" v-if="p.detail">{{ p.detail }}</p>
      <span class="printer-tile-since" v-if="since">{{ since }}</span>
    </template>

    <template v-else>
      <div class="printer-tile-head"><Icon name="printer" :size="18" /><span class="printer-tile-name">{{ p.name }}</span></div>
      <div class="printer-tile-foot">
        <span class="printer-tile-state">{{ p.headline || word }}</span>
        <span class="printer-tile-detail" v-if="p.detail">{{ p.detail }}</span>
      </div>
    </template>
  </button>
</template>
