<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Printers on this Wi-Fi: Add's own section for them (design/printers/AddList, AddAsking, AddAnswers).
 *
 * Separate from "Already waiting" because a printer is added differently, and a household should know
 * that before it taps, not after: the hub does not let itself in. It asks; the printer shows the ask on
 * its own screen; somebody standing at it taps Allow -- or a phone that already has that printer, at
 * home. So the tap here asks, and the row it was on GROWS IN PLACE into what to do, named for the
 * printer -- "Tap Allow on OBI1's screen" -- with how long the ask has left and a way to stop asking,
 * because somebody who walked to the wrong printer should not have to wait out the clock.
 *
 * Then it answers, in the row that asked: let in, said no, nobody answered, or could not reach. Every
 * row keeps its place, saying what it now is (AGENTS.md section 4), and the answered ones leave when Add
 * is next opened -- the brain puts them away then (POST /printers/look). All the words in a row are the
 * brain's (Printers.ask_words); this file draws them.
 *
 * The board shows the printer's own screen beside the asking row. That is an illustration of where to
 * look, copied from the printer's software for the board's sake, and it is not drawn here: a picture of
 * a screen this panel cannot see would be a picture that can be wrong.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { askPrinter, lookForPrinters, stopAsking, type PrinterAsk } from './api'
import { applyPrinters, clockNow, loadPrinters, notify, store } from './store'
import { homeTab } from './layout'
import Icon from './Icon.vue'

/* Asked for again the moment Add opens: the Look half of the knock decision (design/knock/). It is also
   when the brain puts last visit's answers away. */
onMounted(async () => {
  if (!store.printers) return
  try { applyPrinters(await lookForPrinters()) } catch { /* the background look stands */ }
})

/* The rows, in the order they first appeared, so a printer let in keeps its place in the list rather
   than jumping out of "found" and into nothing. */
const order = ref<string[]>([])
const found = computed(() => store.printers?.found ?? [])
const asks = computed(() => new Map((store.printers?.asks ?? []).map(a => [a.id, a])))
watch([found, asks], () => {
  for (const id of [...asks.value.keys(), ...found.value.map(f => f.id)]) if (!order.value.includes(id)) order.value.push(id)
}, { immediate: true })
type Row = { id: string; name: string; ask: PrinterAsk | null }
const rows = computed<Row[]>(() => order.value.flatMap(id => {
  const ask = asks.value.get(id) ?? null
  const f = found.value.find(x => x.id === id)
  return f || ask ? [{ id, name: f?.name ?? ask!.name, ask }] : []
}))

/* the countdown: the printer's own clock, from when the brain asked */
const now = ref(Date.now())
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(tick))
const left = (a: PrinterAsk) => Math.max(0, Math.round((a.until ?? 0) - now.value / 1000))
const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const ASK_LASTS = 120

const busy = ref('')
async function ask(id: string) {
  if (busy.value) return
  busy.value = id
  try { applyPrinters(await askPrinter(id)); loadPrinters() } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
async function stop(id: string) {
  try { applyPrinters(await stopAsking(id)) } catch (e: any) { notify(e.message, 'error') }
}
function open(id: string) { store.sheet = null; store.printer = id }
/* "It's on Your afternoon now" -- where the print went, by the name the wall's own first tab has. */
const where = computed(() => homeTab(new Date(clockNow()).getHours()))
const printing = (id: string) => store.printers?.printers.some(p => p.id === id && p.state === 'printing')
</script>

<template>
  <div class="add-block" v-if="rows.length">
    <h3 class="label">Printers on this Wi‑Fi</h3>
    <ul class="printer-rows">
      <li v-for="r in rows" :key="r.id" :class="['printer-row', r.ask?.state ?? 'nearby']">
        <!-- asking: the row is the instruction -->
        <template v-if="r.ask?.state === 'waiting'">
          <div class="printer-asking">
            <span class="printer-asking-head"><span class="printer-icon"><Icon name="printer" :size="19" /></span>Asking {{ r.name }}</span>
            <h4 class="printer-asking-title display">{{ r.ask.title }}</h4>
            <p class="printer-asking-sub">{{ r.ask.detail }}</p>
            <div class="printer-asking-foot">
              <svg class="printer-ring" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <circle cx="12" cy="12" r="9.5" />
                <circle cx="12" cy="12" r="9.5" class="left" :style="{ strokeDasharray: `${(left(r.ask) / ASK_LASTS) * 59.7} 59.7` }" />
              </svg>
              <span class="printer-asking-left"><b>{{ clock(left(r.ask)) }}</b> left</span>
              <button class="button small ghost" @click="stop(r.id)">Stop asking</button>
            </div>
          </div>
        </template>
        <template v-else>
          <span class="printer-icon" :class="{ plain: r.ask && r.ask.state !== 'allowed' }"><Icon :name="r.ask?.state === 'allowed' ? 'check' : 'printer'" :size="19" /></span>
          <span class="printer-text">
            <span class="printer-title">{{ r.ask?.title ?? r.name }}</span>
            <span class="printer-sub">{{ r.ask ? r.ask.detail : '3D printer' }}<template v-if="r.ask?.state === 'allowed' && printing(r.id)"> It’s on {{ where }} now.</template></span>
          </span>
          <button v-if="r.ask?.state === 'allowed'" class="button small" @click="open(r.id)">Open</button>
          <button v-else-if="r.ask" class="button small ghost" :class="{ busy: busy === r.id }" @click="ask(r.id)">Ask again</button>
          <button v-else class="button small" :class="{ busy: busy === r.id }" @click="ask(r.id)">Add</button>
        </template>
      </li>
    </ul>
  </div>
</template>
