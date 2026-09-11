<script setup lang="ts">
/*
 * The way around the house, across the top: the clock, three tabs, and the two
 * things the side list used to keep in reach -- adding a device, and whether
 * the hub is connected. Chosen in How the house looks; see layout.ts.
 */
import { computed } from 'vue'
import { store } from './store'
import Icon from './Icon.vue'

const props = defineProps<{ clock: string; day: string; now: Date; tab: 'home' | 'rooms' | 'cameras'; inRoom: boolean }>()
const emit = defineEmits<{ go: [tab: 'home' | 'rooms' | 'cameras'] }>()

/* the first tab is named for the time of day, the way the greeting is */
const yours = computed(() => {
  const h = props.now.getHours()
  return h < 5 ? 'Your night' : h < 12 ? 'Your morning' : h < 17 ? 'Your afternoon' : h < 21 ? 'Your evening' : 'Your night'
})
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
      <button v-for="t in tabs" :key="t.id" class="tab" :class="{ active: tab === t.id && !(inRoom && t.id === 'home') }" @click="emit('go', t.id)">
        <Icon :name="t.icon" :size="16" /><span>{{ t.label }}</span>
      </button>
    </nav>
    <div class="topbar-right">
      <span class="link" :class="{ up: store.linkUp }">{{ store.linkUp ? 'Connected' : 'Reconnecting' }}</span>
      <button class="topbar-add" :class="{ attention: store.found.length }" @click="store.sheet = 'add'" :aria-label="store.found.length ? `Add a device, ${store.found.length} found nearby` : 'Add a device'">
        <Icon name="plus" :size="18" />
      </button>
    </div>
  </header>
</template>
