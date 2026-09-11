<script setup lang="ts">
import { ref } from 'vue'
import { store, notify } from './store'
import { allowPhone, denyPhone, type Ask } from './api'
import Icon from './Icon.vue'

/* A phone on the Wi‑Fi asked to join. Shown on every screen that is already in; allowing needs the code, and the code
   prompt appears on its own. Let in for a day, a weekend, or for good; every phone starts home-only.

   On its look, checked rendered at midday and at midnight: this card deliberately does NOT take its colour from the
   sky the way tiles and room cards do. It is the one place a person hands out keys to the house, so it has to look
   the same at every hour — recognising it instantly, and noticing when something about it is off, is the only
   defence a person has against answering a prompt they should not. The cost is that at a bright hour it stays dark
   while everything around it goes pale. It still reads as a deliberate card rather than a hole punched in the
   daylight, for three reasons, and only the first is an accident of arrangement: the scene bar sits beneath it with
   the same dark treatment, so the two read as one band; it carries a lit edge; and it holds its own buttons. If a
   layout ever leaves it alone among pale cards, lift it with elevation — a shadow — and never with hue. */
const choosing = ref<string | null>(null), busy = ref(false)
const SPANS = [['day', 'For today'], ['weekend', 'For the weekend'], ['keep', 'Keep']] as const
async function allow(a: Ask, span: 'day' | 'weekend' | 'keep') {
  if (busy.value) return
  busy.value = true
  try { await allowPhone(a.id, span); notify(`${a.name} is in${span === 'day' ? ' for today' : span === 'weekend' ? ' for the weekend' : ''}.`) }
  catch (e: any) { if (e.message !== 'That needs the code.') notify(e.message, 'error') }
  choosing.value = null; busy.value = false
}
async function deny(a: Ask) { try { await denyPhone(a.id) } catch (e: any) { if (e.message !== 'That needs the code.') notify(e.message, 'error') } }
</script>

<template>
  <div class="nudge ask" v-for="a in store.asks" :key="a.id">
    <span class="nudge-icon"><Icon name="phone" :size="20" /></span>
    <span class="nudge-text">
      <span class="nudge-title">{{ a.name }} wants to join the house</span>
      <span class="nudge-sub">{{ choosing === a.id ? 'For how long?' : 'Let in, it can run the house from the Wi‑Fi. Not sure whose it is? Not now.' }}</span>
    </span>
    <span class="ask-actions" v-if="choosing !== a.id">
      <button class="button small" @click="choosing = a.id">Allow</button>
      <button class="button small ghost" @click="deny(a)">Not now</button>
    </span>
    <span class="ask-actions" v-else>
      <button class="button small" v-for="[k, l] in SPANS" :key="k" :class="{ busy, ghost: k !== 'keep' }" @click="allow(a, k)">{{ l }}</button>
    </span>
  </div>
</template>
