<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/* What the lights tell you: the house's four -- arriving, leaving, a door left open, something nearly
   done -- then the household's own, from Routines. Each row has its switch and a Try, and a try opens
   in place under its row with the two ways to check it, then the step-by-step report of what the house
   saw. design/signal/Chosen.dc.html and Walked.dc.html; the arrangement lives in signals.ts. */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify, loadSignals, loadRoutines } from './store'
import { trySignal, stopTrying, setSignalOn, enableRoutine, showEnd, setHouseEnd } from './api'
import { rowsOf, preview, emitter, triedLine, triedOk, tryOf, endsToAsk, headline, mark, stepTime, type Row } from './signals'

const rows = computed(() => rowsOf(store.signals))
const open = ref('')              // the row whose Try is open
const busy = ref('')
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | undefined

onMounted(() => { loadSignals(); clock = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => clock && clearInterval(clock))

const trying = (r: Row) => tryOf(store.signals, r.key)
/* A try that is running or just finished shows its report; otherwise the open row offers the two ways. */
const report = (r: Row) => { const t = trying(r); return t && open.value === r.key ? t : null }

function toggleOpen(r: Row) {
  const t = trying(r)
  if (open.value === r.key) {
    if (t?.state === 'watching') stopTrying().then(loadSignals)
    open.value = ''
  } else open.value = r.key
}
async function go(r: Row, how: 'now' | 'watch') {
  busy.value = r.key + how
  try { await trySignal(r.key, how); await loadSignals() } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
async function flip(r: Row) {
  if (!r.available) return
  busy.value = 'flip' + r.key
  try {
    if (r.rule) { await enableRoutine(r.rule, !r.on); loadRoutines() } else await setSignalOn(r.key, !r.on)
    await loadSignals()
  } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}

/* Which end is the house: asked once per strip, the way setup asks everything about a strip -- by
   lighting it, and asking what somebody can see. */
const asking = ref('')
async function light(strip: string) { asking.value = strip; try { await showEnd(strip) } catch (e: any) { notify(e.message, 'error') } }
async function answer(strip: string, house: 'plug' | 'far') {
  try { store.signals = await setHouseEnd(strip, house); asking.value = '' } catch (e: any) { notify(e.message, 'error') }
}
const stripName = (id: string) => {
  const s = store.signals?.strips.find(x => x.id === id)
  const d = s?.device ? store.rooms.flatMap(r => r.devices).find(x => x.hw === s.device && x.capability === 'light') : null
  return d?.name ?? 'the light strip'
}
</script>

<template>
  <div class="page">
    <p class="page-lede">A few things worth knowing without looking at a screen. Each shows on the lights near where it happens, then they go back to how they were.</p>

    <template v-for="group in (['house', 'own'] as const)" :key="group">
      <h3 class="label routines-head" v-if="group === 'own' && rows.own.length">Your own · from Routines</h3>
      <ul class="sig-list" v-if="rows[group].length">
        <li v-for="r in rows[group]" :key="r.key" class="sig-row" :class="{ 'sig-off': !r.on, 'sig-na': !r.available, 'sig-opened': open === r.key }">
          <span class="routine-text">
            <span class="routine-name">{{ r.name }}</span>
            <span class="routine-sub sig-tried" v-if="triedLine(r.key)" :class="{ 'sig-bad': !triedOk(r.key) }">{{ triedLine(r.key) }}</span>
            <span class="routine-sub" v-else>{{ r.own ? 'A routine you asked for' : r.hint }}</span>
          </span>
          <span class="sig-run" :class="'pv-' + preview(r.kind, r.toward)" :style="{ '--c': emitter(r.rgb) }" aria-hidden="true"><span></span></span>
          <button v-if="r.available" class="button small sig-try" :class="{ ghost: open !== r.key }" @click="toggleOpen(r)">
            {{ open === r.key ? (trying(r)?.state === 'watching' ? 'Stop' : 'Close') : triedLine(r.key) ? 'Try again' : 'Try' }}
          </button>
          <span v-else></span>
          <button class="toggle" role="switch" :aria-checked="r.on" :aria-label="`${r.name}: ${r.on ? 'on' : 'off'}`" :disabled="!r.available"
                  :class="{ on: r.on, busy: busy === 'flip' + r.key }" @click="flip(r)"><span class="knob"></span></button>

          <div class="sig-open" v-if="open === r.key">
            <!-- the report: what the house saw, one link of the chain at a time -->
            <template v-if="report(r)">
              <div class="sig-head">
                <span class="routine-name">{{ headline(report(r)!, now).title }}</span>
                <span class="routine-sub" v-if="headline(report(r)!, now).sub">{{ headline(report(r)!, now).sub }}</span>
              </div>
              <ol class="sig-steps">
                <li v-for="s in report(r)!.steps" :key="s.key" :class="'st-' + s.state">
                  <span class="sig-mark">{{ mark(s.state) }}</span>
                  <span class="routine-text"><span class="sig-step">{{ s.text }}</span><span class="routine-sub" v-if="s.sub">{{ s.sub }}</span></span>
                  <span class="sig-at">{{ stepTime(s.at) }}</span>
                </li>
              </ol>
              <div class="sig-again" v-if="report(r)!.state !== 'watching' && report(r)!.state !== 'running'">
                <button class="button small ghost" @click="go(r, 'now')" :class="{ busy: busy === r.key + 'now' }">Show me now</button>
                <button class="button small ghost" @click="go(r, 'watch')" :class="{ busy: busy === r.key + 'watch' }">Watch again</button>
              </div>
            </template>

            <!-- or the two ways to check it -->
            <template v-else>
              <div class="sig-ends" v-for="sid in endsToAsk(store.signals, r.kind)" :key="sid">
                <span class="routine-text">
                  <span class="sig-step">Which end of {{ stripName(sid) }} is nearer the house?</span>
                  <span class="routine-sub">{{ asking === sid ? 'One end is lit on the strip now.' : 'It lights one end so you can tell.' }}</span>
                </span>
                <span class="sig-again" v-if="asking === sid">
                  <button class="button small" @click="answer(sid, 'plug')">The lit end</button>
                  <button class="button small ghost" @click="answer(sid, 'far')">The other end</button>
                </span>
                <button v-else class="button small ghost" @click="light(sid)">Light one end</button>
              </div>
              <div class="sig-ways">
                <button class="sig-way" @click="go(r, 'now')" :class="{ busy: busy === r.key + 'now' }">
                  <span class="sig-way-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 5v14l11-7z" /></svg></span>
                  <span class="routine-text"><span class="sig-step">Show me now</span><span class="routine-sub">Plays it once on its lights, even in daylight, then puts them back. Checks the lights.</span></span>
                </button>
                <button class="sig-way" @click="go(r, 'watch')" :class="{ busy: busy === r.key + 'watch' }">
                  <span class="sig-way-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg></span>
                  <span class="routine-text"><span class="sig-step">Wait for the real thing</span><span class="routine-sub">For 10 minutes the house watches for it happening, and tells you each step it saw. Checks everything.</span></span>
                </button>
              </div>
              <p class="routine-sub sig-aside">“After dark” is set aside while you try, so a test at noon does not fail for being at noon.</p>
            </template>
          </div>
        </li>
      </ul>
    </template>

    <p class="page-foot">Want the lights to say something else? Ask for it in <button class="linkish" @click="store.sheet = 'routines'">Routines</button>, in your own words. It lands here once you approve it, with the same Try.</p>
  </div>
</template>
