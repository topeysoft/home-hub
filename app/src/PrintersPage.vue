<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Printers: every 3D printer in the house, printing or not (design/printers/AddAnswers, the door on the left).
 *
 * Under B a print leads Your afternoon while it lasts, and a printer a household put in a room is a tile
 * there; a printer with neither -- C3PO, ready, with no room -- has to live somewhere a person can find it,
 * and this is that place. It is also where one is forgotten: the hub comes off the printer's own list of
 * devices too (DELETE /printers/{id}), so it asks first, with the name in the question, the way removing
 * a thing does on Needs a look. A forgotten row stays, saying so, until the page is closed.
 */
import { computed, ref } from 'vue'
import { forgetPrinter } from './api'
import { applyPrinters, notify, store } from './store'
import { printerChip } from './printers'
import Icon from './Icon.vue'

const printers = computed(() => store.printers?.printers ?? [])
const asking = ref('')
const busy = ref('')
const gone = ref<Record<string, string>>({})     // forgotten while this page was open: the row stays and says so
/* What the row says: the printer's word and where it is. "OBI1 printing, 42%", "In the Office". */
const line = (id: string) => {
  const p = printers.value.find(x => x.id === id); if (!p) return ''
  const doing = printerChip(p).slice(p.name.length).trim()
  return [doing ? doing[0].toUpperCase() + doing.slice(1) : '', p.room ? `in the ${p.room.name}` : 'no room'].filter(Boolean).join(', ')
}
const shown = computed(() => [...printers.value.map(p => ({ id: p.id, name: p.name })),
  ...Object.entries(gone.value).filter(([id]) => !printers.value.some(p => p.id === id)).map(([id, name]) => ({ id, name }))])

async function forget(id: string, name: string) {
  if (busy.value) return
  busy.value = id
  try { applyPrinters(await forgetPrinter(id)); gone.value = { ...gone.value, [id]: name }; asking.value = '' }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
function open(id: string) { store.sheet = null; store.printer = id }
</script>

<template>
  <div class="page">
    <p class="page-lede">The house’s 3D printers. A print shows on the first screen for as long as it lasts; this is where each printer is the rest of the time.</p>
    <ul class="printer-rows" v-if="shown.length">
      <li v-for="r in shown" :key="r.id" class="printer-row" :class="{ forgotten: !!gone[r.id] }">
        <span class="printer-icon" :class="{ plain: !!gone[r.id] }"><Icon name="printer" :size="19" /></span>
        <span class="printer-text">
          <span class="printer-title">{{ r.name }}</span>
          <span class="printer-sub">{{ gone[r.id] ? 'Forgotten. The hub is off its list too.' : line(r.id) }}</span>
        </span>
        <template v-if="!gone[r.id]">
          <span class="printer-ask" v-if="asking === r.id">
            Forget {{ r.name }}? The hub comes off its list of devices too.
            <button class="button small warn" :class="{ busy: busy === r.id }" @click="forget(r.id, r.name)">Yes, forget {{ r.name }}</button>
            <button class="button small ghost" @click="asking = ''">Keep it</button>
          </span>
          <template v-else>
            <button class="button small ghost" @click="asking = r.id">Forget</button>
            <button class="button small" @click="open(r.id)">Open</button>
          </template>
        </template>
      </li>
    </ul>
    <p class="empty" v-else>No printers in the house yet.</p>
    <p class="add-elsewhere" v-if="store.printers?.found.length">
      <Icon name="printer" :size="17" />
      <span>{{ store.printers?.found.length === 1 ? 'Another printer is' : `${store.printers?.found.length} more printers are` }} on the Wi‑Fi. <button class="linky" @click="store.sheet = 'add'">Add to the house</button></span>
    </p>
  </div>
</template>
