<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Which way round: the roofline's order, asked in the yard (design/roofline/TapA.dc.html).
 *
 * Decided 1 October, C then A: the order of the runs is never asked until a chase is first wanted,
 * because only a chase shows the seams. Then the roof is put on show -- every run lit its own color with
 * a white light running the way it goes -- and somebody standing in the yard with a phone taps the colors
 * in the order they would walk past them, twice to turn one round. It opens already filled in from the
 * order the boxes were set up (B's guess), so the common case is one look and one tap.
 *
 * Nothing is named but colors: no word about data, ends, outputs or boxes. The brain decides everything
 * (brain/hub/roofline.py); this draws what it is given and sends back what was tapped.
 */
import { computed, ref } from 'vue'
import { loadRoofline, notify, store } from './store'
import { yardAgain, yardDone, yardKeep, yardLeave, yardTap, type Yard } from './api'
import { nth, yardSub } from './controller'
import Icon from './Icon.vue'

const roof = computed(() => (store.roofline?.exists ? store.roofline : null))
const y = computed<Yard | null>(() => roof.value?.yard ?? null)
const done = computed(() => y.value?.step === 'done')
const busy = ref(false)

async function run(fn: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true
  try {
    const got = await fn()
    if (got && typeof got === 'object' && 'rows' in (got as object) && roof.value) roof.value.yard = got as Yard
    else await loadRoofline()
  } catch (e: any) { notify(e.message, 'error') }
  busy.value = false
}
const tap = (chip: string, n: number) => run(() => yardTap(chip, n))
const again = () => run(yardAgain)
const finish = () => run(yardDone)
async function keep() { await run(yardKeep); store.yard = false; await loadRoofline() }
async function leave() { await run(yardLeave); store.yard = false }

const rows = computed(() => (y.value?.rows ?? []).map((r, i) => ({
  ...r, sub: y.value ? yardSub(y.value, i) : '', end: r.nth != null ? nth(r.nth + 1) : '',
  color: `rgb(${r.led.join(',')})`,
})))
const turned = computed(() => rows.value.filter(r => r.turned).map(r => r.name))
const foot = computed(() => done.value
  ? `${turned.value.length ? `Turned round: ${turned.value.join(' and ')}. ` : ''}Change it any time from the Roofline.`
  : 'Tap them in the order you’d walk past them. If a white light runs toward where you started, tap it twice to turn it round.')
</script>

<template>
  <div class="sheet-back yard-back" v-if="y" @click.self="leave">
    <div class="sheet yard-sheet" role="dialog" aria-label="Which way round?">
      <button class="yard-back-link" @click="leave"><Icon name="back" :size="16" /> Roofline</button>
      <h2 class="display yard-title">{{ done ? 'That’s the way round' : 'Which way round?' }}</h2>
      <p class="yard-lede">{{ done
        ? 'One white light is going round the whole roof now, the way you tapped it. Watch it once.'
        : 'Stand where you can see the roof. Each strip is lit in its own color, with a white light running the way it goes.' }}</p>
      <ul class="yard-rows">
        <li v-for="r in rows" :key="`${r.chip}:${r.run}`">
          <button class="yard-row" :class="{ tapped: r.nth != null }" :disabled="done || busy" @click="tap(r.chip, r.run)">
            <span class="yard-dot" :style="{ background: r.color, boxShadow: `0 0 12px ${r.color}` }"></span>
            <span class="yard-text"><span class="yard-name">{{ r.name }}</span><span class="yard-sub">{{ r.sub }}</span></span>
            <span class="yard-end" :class="{ turned: r.turned }">{{ r.end }}</span>
          </button>
        </li>
      </ul>
      <p class="yard-foot">{{ foot }} <button class="linkish" v-if="!done" @click="again">Start again</button></p>
      <button class="button yard-go" v-if="done" :class="{ busy }" @click="keep">It goes the right way</button>
      <button class="button yard-go" v-else :class="{ busy }" :disabled="!y.all" @click="finish">That’s all of them</button>
    </div>
  </div>
</template>

<style scoped>
/* Scoped: every name here is the yard's and nothing else draws one (AGENTS.md §4). A phone is the
   screen this was drawn for (390 x 844): there the sheet is the whole screen, the way TapA draws it. */
.yard-sheet {
  display: flex; flex-direction: column; width: 420px; max-height: calc(100dvh - 48px);
  padding: 22px 22px 24px; overflow: auto;
}
@media (max-width: 520px) {
  .yard-back { padding: 0; }
  .yard-sheet { width: 100%; height: 100dvh; max-height: none; border-radius: 0; padding: 64px 22px 30px; }
}
.yard-back-link { align-self: flex-start; display: inline-flex; align-items: center; gap: 4px; font-size: 15px; color: var(--ink-2); background: none; border: 0; padding: 0; }
.yard-title { flex: none; margin: 18px 0 0; font-size: 30px; }
.yard-lede { margin: 10px 0 0; font-size: 15px; line-height: 1.45; color: var(--ink-2); }
.yard-rows { list-style: none; margin: 18px 0 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.yard-row {
  width: 100%; display: grid; grid-template-columns: 30px 1fr auto; gap: 12px; align-items: center; text-align: left;
  padding: 12px 14px; border-radius: 18px; border: 0; color: var(--ink); background: rgba(255, 255, 255, 0.04);
}
.yard-row.tapped { background: rgba(255, 255, 255, 0.08); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14); }
.yard-row:disabled { opacity: 1; }
.yard-dot { width: 22px; height: 22px; border-radius: 50%; }
.yard-name { display: block; font-size: 17px; font-weight: 500; }
.yard-sub { display: block; font-size: 13.5px; line-height: 1.3; color: var(--ink-2); }
.yard-end { font-size: 14px; font-weight: 500; }
.yard-end.turned { color: var(--lamp); }
.yard-foot { margin: 14px 0 0; font-size: 14px; line-height: 1.45; color: var(--muted); }
.yard-go { margin-top: auto; height: 52px; font-size: 16px; justify-content: center; }
@media (min-width: 521px) { .yard-go { margin-top: 18px; } }
</style>
