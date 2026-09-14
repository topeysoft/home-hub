<script setup lang="ts">
/* The Cameras tab of the Top navigation: every camera in the house, each a
   tap to watch and a hold to open. */
import { computed } from 'vue'
import type { Room } from '../api'
import { cap, store } from '../store'
import { useArrive } from '../arrive'
import CameraTile from '../tiles/CameraTile.vue'

const props = defineProps<{ rooms: Room[]; woke?: number }>()
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))
/* Home's row arrives from the right because it sweeps right, and the travel is
   what teaches the sweep. Nothing sweeps here -- this is a grid that wraps and
   runs DOWN -- so the frames come up from below instead, which is where the rest
   of them are. Same entrance, pointed at the gesture this screen actually has. */
const flow = useArrive(() => !cameras.value.length, () => props.woke)
</script>

<template>
  <section class="home">
    <header class="stage-head"><h1 class="display">Cameras</h1></header>
    <div class="camera-row cameras-all" :class="flow" v-if="cameras.length">
      <CameraTile v-for="(c, i) in cameras" :key="c.id" :device="c" :style="{ '--flow-i': i }" v-hold="() => (store.opened = c)" />
    </div>
    <p class="empty" v-else>No cameras yet. Add one and it shows up here on its own.</p>
  </section>
</template>
