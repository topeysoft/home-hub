<script setup lang="ts">
import { computed } from 'vue'
import { activity, roomActive, cap, store } from '../store'
import type { Room } from '../api'
import Icon from '../Icon.vue'

const props = defineProps<{ rooms: Room[]; hour: number }>()
defineEmits<{ open: [id: string] }>()

const greeting = computed(() => props.hour < 5 ? 'Good night' : props.hour < 12 ? 'Good morning' : props.hour < 17 ? 'Good afternoon' : props.hour < 21 ? 'Good evening' : 'Good night')
const summary = computed(() => {
  const active = props.rooms.filter(roomActive)
  if (!store.loaded) return store.error || 'Finding the house…'
  if (!active.length) return 'The house is quiet.'
  return active.length === 1 ? `Something is on in the ${active[0].name}.` : `Something is on in ${active.length} rooms.`
})
const kinds = (r: Room) => [...new Set(r.devices.map(cap))].filter(k => k !== 'sensor').slice(0, 4)
</script>

<template>
  <section class="home">
    <header class="stage-head">
      <h1 class="display">{{ greeting }}</h1>
      <p class="lede">{{ summary }}</p>
    </header>
    <div class="room-grid">
      <button v-for="r in rooms" :key="r.id" class="room-card" :class="{ active: roomActive(r), empty: !r.devices.length }" @click="$emit('open', r.id)">
        <div class="room-card-top">
          <span class="room-kinds"><Icon v-for="k in kinds(r)" :key="k" :name="k" :size="16" /></span>
        </div>
        <div class="room-card-name display">{{ r.name }}</div>
        <div class="room-card-activity">{{ activity(r) }}</div>
      </button>
    </div>
  </section>
</template>
