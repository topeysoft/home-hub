<script setup lang="ts">
/* Every room as a card, one place rather than one per layout: the same grid on
   the Stack home, the Rail home, and the Rooms tab, so a room card looks and
   behaves the same wherever a person finds it. */
import type { Room } from './api'
import { activity, roomActive } from './store'
import Icon from './Icon.vue'

defineProps<{ rooms: Room[] }>()
defineEmits<{ open: [id: string] }>()

/* the one number worth a glance on a room card: its temperature, when a sensor in the room reads one */
function temp(r: Room): string {
  const d = r.devices.find(d => d.capability === 'sensor.temperature' && Number.isFinite(Number(d.state)))
  return d ? `${Math.round(Number(d.state))}°` : ''
}
</script>

<template>
  <div class="room-grid">
    <button v-for="r in rooms" :key="r.id" class="room-card" :class="{ active: roomActive(r), empty: !r.devices.length, attention: r.id === 'unassigned' }" @click="$emit('open', r.id)">
      <div class="room-card-top">
        <span class="room-temp" v-if="temp(r)"><Icon name="sensor" :size="14" />{{ temp(r) }}</span>
      </div>
      <div class="room-card-name">{{ r.name }}</div>
      <div class="room-card-activity">{{ activity(r) }}</div>
    </button>
  </div>
</template>
