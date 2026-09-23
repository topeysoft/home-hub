<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The way around the house, across the top: the clock, three tabs, and the two
 * things the side list used to keep in reach -- adding a device, and whether
 * the hub is connected -- plus the one door to everything else, This house.
 * Chosen in How the house looks; see layout.ts.
 */
import { computed } from 'vue'
import { stripWaiting } from './adding'
import { store, updateReady, weatherParts } from './store'
import Icon from './Icon.vue'
import WeatherArt from './WeatherArt.vue'

const props = defineProps<{ clock: string; day: string; now: Date; tab: 'home' | 'rooms' | 'cameras'; inRoom: boolean }>()
const emit = defineEmits<{ go: [tab: 'home' | 'rooms' | 'cameras'] }>()

/* the first tab is named for the time of day, the way the greeting is */
const yours = computed(() => {
  const h = props.now.getHours()
  return h < 5 ? 'Your night' : h < 12 ? 'Your morning' : h < 17 ? 'Your afternoon' : h < 21 ? 'Your evening' : 'Your night'
})
/* The sky, in the bar, and only where a phone has taken it out of the stage --
   see the Wall's phone rules in panel.css, and design/phone/Main.dc.html. It is
   rendered always and hidden by CSS rather than switched here, because whether
   there is room for it is a question about the width of the screen and belongs
   where the widths are. The number only: the drawing IS the condition, and the
   words do not fit a 390px bar on the day the forecast says "Unusual weather". */
const temp = computed(() => weatherParts().temp)

/* Things waiting to be set up: found on the network, and a strip still knocking. One number,
   because to a household they are the same sentence -- something new, not set up yet. */
const waiting = computed(() => store.found.length + (stripWaiting(store.strip?.state) ? 1 : 0))

const tabs = computed(() => [
  { id: 'home' as const, label: yours.value, icon: 'home' },
  { id: 'rooms' as const, label: 'Rooms', icon: 'switch' },
  { id: 'cameras' as const, label: 'Cameras', icon: 'camera' },
])
</script>

<template>
  <header class="topbar">
    <div class="topbar-clock">
      <span class="topbar-time display">{{ clock }}</span>
      <span class="topbar-day">{{ day }}</span>
    </div>
    <nav class="tabs" aria-label="Around the house">
      <!-- as drawn: the house glyph leads, the tabs are words -->
      <button v-for="t in tabs" :key="t.id" class="tab" :class="{ active: tab === t.id && !(inRoom && t.id === 'home') }" @click="emit('go', t.id)">
        <Icon v-if="t.id === 'home'" :name="t.icon" :size="16" /><span>{{ t.label }}</span>
      </button>
    </nav>
    <div class="topbar-right">
      <span class="topbar-wx" v-if="temp" :aria-label="`Outside, ${temp}`">
        <WeatherArt class="topbar-cloud" />
        <span class="topbar-temp">{{ temp }}</span>
      </span>
      <span class="link" :class="{ up: store.linkUp }">{{ store.linkUp ? 'Connected' : 'Reconnecting' }}</span>
      <!-- The dot is the quiet half of an arrival and it does not fold: a knock's line in the band
           stops shouting after an hour, and this stays for as long as the thing is knocking, so the
           house goes quiet without forgetting. design/knock/. -->
      <button class="topbar-add" :class="{ attention: waiting }" @click="store.sheet = 'add'" :aria-label="waiting ? `Add to the house, ${waiting} waiting` : 'Add to the house'">
        <Icon name="plus" :size="18" />
      </button>
      <button class="topbar-add topbar-house" :class="{ attention: updateReady() }" @click="store.sheet = 'house'" :aria-label="updateReady() ? 'This house, an update is ready' : 'This house'">
        <Icon name="menu" :size="18" />
      </button>
    </div>
  </header>
</template>
