<script setup lang="ts">
/* The Rooms tab of the Top navigation: every room as a card. With the side
   list gone this is where the whole house is seen at once. */
import type { Room } from '../api'
import RoomGrid from '../RoomGrid.vue'

defineProps<{ rooms: Room[] }>()
defineEmits<{ open: [id: string] }>()
</script>

<template>
  <section class="home">
    <header class="stage-head"><h1 class="display">Rooms</h1></header>
    <RoomGrid :rooms="rooms" @open="$emit('open', $event)" />
  </section>
</template>
