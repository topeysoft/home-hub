<script setup lang="ts">
import { ref } from 'vue'
import { store, notify } from './store'
import { allowPhone, denyPhone, type Ask } from './api'
import Icon from './Icon.vue'

/* A phone on the Wi‑Fi asked to join. Shown on every screen that is already in; allowing needs the code, and the code
   prompt appears on its own. Let in for a day, a weekend, or for good; every phone starts home-only. */
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
