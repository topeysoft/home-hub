<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Which screen the app is on. /add, or no houses yet: adding one (AppSafari, AppFirst, AppName). Otherwise a
 * house -- the one whose Wi-Fi this phone is on, else the one opened last (design/houses/, B) -- with Houses
 * over it when somebody taps the house's name.
 */
import { onMounted, ref } from 'vue'
import { houseToOpen, load, reach, state, type House } from './houses'
import AddView from './AddView.vue'
import HouseView from './HouseView.vue'

const view = ref<'loading' | 'add' | 'house'>('loading')
const current = ref<string | null>(null)
const bases = ref<Record<string, string>>({})

async function reachAll() {
  await Promise.all(state.houses.map(async (h: House) => {
    const got = await reach(h)
    h.reach = got.reach; bases.value[h.id] = got.base
  }))
}

onMounted(async () => {
  await load()
  if (location.pathname.startsWith('/add') || !state.houses.length) { view.value = 'add'; return }
  // A house answering at home opens at once; otherwise the one opened last, once everybody has been asked.
  const all = reachAll()
  await Promise.race([all, new Promise(r => setTimeout(r, 1700))])
  current.value = houseToOpen(state.houses)
  view.value = 'house'
  all.then(() => { if (!current.value) current.value = houseToOpen(state.houses) })
})

function open(id: string) {
  current.value = id
  view.value = 'house'
  if (location.pathname !== '/') history.replaceState(null, '', '/')
}
function adding() { view.value = 'add'; history.pushState(null, '', '/add') }
</script>

<template>
  <AddView v-if="view === 'add'" @added="open" @cancel="state.houses.length && open(houseToOpen(state.houses)!)" />
  <HouseView v-else-if="view === 'house' && current" :key="current" :id="current" :base="bases[current] ?? ''" @switch="open" @add="adding" @reached="(id, b) => (bases[id] = b)" />
</template>
