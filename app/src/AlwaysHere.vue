<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/* What this phone keeps on Home, on or off (design/home-keep/KeepBPhone). A block of its own above On right now,
   because a thing that is off under a heading that says on is the one lie this screen could tell. The same chips
   as On right now, and the same tap: it turns the thing on or off, and the chip stays where it is either way. */
import { computed } from 'vue'
import type { Device } from './api'
import { cap, deviceById, isActive, perform, roomOf, shortName, store } from './store'
import { alwaysIds } from './onhome'
import Icon from './Icon.vue'

const rows = computed(() => alwaysIds().map(deviceById).filter((d): d is Device => !!d && !d.attrs?.off_home))

const place = (d: Device) => roomOf(d)?.name ?? ''
const line = (d: Device) => isActive(d) ? place(d) : [place(d), 'Off'].filter(Boolean).join(' · ')
const hint = (d: Device) => isActive(d) ? 'Tap to turn off' : 'Tap to turn on'
async function tap(d: Device) {
  if (store.pending[d.id]) return
  const on = isActive(d)
  await perform(d, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' })
}
</script>

<template>
  <div class="onnow" v-if="rows.length" role="group" aria-label="Always here">
    <button v-for="d in rows" :key="d.id" class="onnow-chip" :class="[cap(d), { unlit: !isActive(d), pending: store.pending[d.id] }]"
            :title="hint(d)" :aria-label="`${shortName(d, roomOf(d))}, ${line(d)}. ${hint(d)}`" @click="tap(d)"
            v-hold="() => (store.opened = d)">
      <span class="onnow-icon"><Icon :name="cap(d)" :size="16" /></span>
      <span class="onnow-text"><span class="onnow-name">{{ shortName(d, roomOf(d)) }}</span><span class="onnow-place">{{ line(d) }}</span></span>
    </button>
  </div>
</template>
