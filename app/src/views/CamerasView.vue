<script setup lang="ts">
/* The Cameras tab of the Top navigation: every camera in the house, each a
   tap to watch and a hold to open. */
import { computed } from 'vue'
import type { Room } from '../api'
import { cap, store } from '../store'
import CameraTile from '../tiles/CameraTile.vue'

const props = defineProps<{ rooms: Room[] }>()
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))
</script>

<template>
  <section class="home">
    <header class="stage-head"><h1 class="display">Cameras</h1></header>
    <div class="camera-row cameras-all" v-if="cameras.length">
      <CameraTile v-for="c in cameras" :key="c.id" :device="c" v-hold="() => (store.opened = c)" />
    </div>
    <p class="empty" v-else>No cameras yet. Add one and it shows up here on its own.</p>
  </section>
</template>
