<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * A print, leading Your afternoon the way a show that is playing leads it (design/printers/NowB, StatesB).
 *
 * The camera across the top, and one pane of glass over its foot with the part's picture and name, how
 * far, and when it will be done. The same card in each of the printer's states, and only the glass
 * changes: printing says how far; waiting for you says the printer's question and offers its own two
 * answers -- the only state with buttons on the card, because the question is the reason it is there;
 * done is drained and says when it finished; stopped mid-print turns the fault color in place.
 *
 * NO BUTTONS WHILE IT PRINTS. A sleeve brushing a kitchen wall must not pause a three-hour print, so the
 * whole card is one way in -- to the printer's pane, where Pause and Stop are -- and nothing else.
 *
 * `compact` is the phone's: the camera on the left, how far and when on the right (PhoneB).
 */
import { computed, ref } from 'vue'
import type { Printer, PrinterAction } from '../api'
import { apiUrl } from '../door'
import { printerAction } from '../api'
import { clockNow, notify, store } from '../store'
import { cardLook, doneAt, finishedLine, layerLine, percent, timeLeft, wallActions, whoLine } from '../printers'
import { locale } from '../lang'
import Icon from '../Icon.vue'

const props = defineProps<{ printer: Printer; compact?: boolean }>()

const p = computed(() => props.printer)
const look = computed(() => cardLook(p.value))
const pct = computed(() => percent(p.value))
const chip = computed(() => ({ printing: 'Live', waiting: 'Waiting for you', done: 'Done', fault: 'Stopped' })[look.value])
/* The camera may not be there -- a printer without one, or one that is not answering -- and then the
   card is the part's own picture on the dark, rather than a broken image. */
const camOk = ref(true)
const thumbOk = ref(true)
const busy = ref('')
async function answer(a: PrinterAction) {
  if (busy.value) return
  busy.value = a.id
  try { await printerAction(p.value.id, a.id, a.args) } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
const open = () => (store.printer = p.value.id)
</script>

<template>
  <article class="tile print-card" :class="[look, { compact }]" role="button" tabindex="0"
           :aria-label="`${p.name}: ${p.job?.name ?? p.headline}`" @click="open" @keydown.enter="open">
    <div class="print-cam">
      <img v-if="camOk" :src="apiUrl(p.camera)" alt="" @error="camOk = false" />
      <img v-else-if="p.job?.thumbnail && thumbOk" class="print-cam-part" :src="apiUrl(p.job.thumbnail)" alt="" @error="thumbOk = false" />
      <span class="print-chip" :class="look"><i></i>{{ chip }}</span>
    </div>

    <div class="print-sheet">
      <div class="print-who">
        <span class="print-thumb"><img v-if="p.job?.thumbnail && thumbOk" :src="apiUrl(p.job.thumbnail)" alt="" @error="thumbOk = false" /><Icon v-else name="printer" :size="20" /></span>
        <span class="print-names">
          <span class="print-part">{{ p.job?.name ?? p.name }}</span>
          <span class="print-sub">{{ whoLine(p) }}</span>
        </span>
      </div>

      <template v-if="look === 'printing'">
        <div class="print-how">
          <span class="print-pct display">{{ pct ?? 0 }}%</span>
          <span class="print-when" v-if="p.job?.remaining_s != null || p.job?.eta_clock">Done at<b>{{ doneAt(p, clockNow(), locale()) }}</b></span>
        </div>
        <div class="print-bar"><i :style="{ width: `${pct ?? 0}%` }"></i></div>
        <div class="print-foot" v-if="!compact"><span>{{ layerLine(p) }}</span><span>{{ timeLeft(p) }}</span></div>
        <p class="print-due" v-else-if="p.job?.remaining_s != null || p.job?.eta_clock">Done at <b>{{ doneAt(p, clockNow(), locale()) }}</b></p>
      </template>

      <template v-else>
        <h3 class="print-says display">{{ p.headline }}</h3>
        <p class="print-detail" v-if="p.detail && !compact">{{ p.detail }}</p>
        <!-- the printer's question has the printer's own two answers, in its own order -->
        <div class="print-answers" v-if="look === 'waiting' && wallActions(p).length && !compact">
          <button v-for="a in wallActions(p).slice(0, 2)" :key="a.id" class="print-answer" :class="{ primary: a.primary, busy: busy === a.id }"
                  :disabled="!!busy" @click.stop="answer(a)">
            <Icon v-if="a.id === 'swap_slot'" name="swap" :size="16" />{{ a.label }}
          </button>
        </div>
        <p class="print-finished" v-if="look === 'done' && finishedLine(p, locale())"><Icon name="check" :size="16" />{{ finishedLine(p, locale()) }}</p>
      </template>
    </div>
  </article>
</template>
