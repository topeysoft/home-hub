<script setup lang="ts">
import { computed, ref } from 'vue'
import { activity, cap } from '../store'
import type { Room } from '../api'
import Icon from '../Icon.vue'
import SceneBar from '../SceneBar.vue'
import LightTile from '../tiles/LightTile.vue'
import MediaTile from '../tiles/MediaTile.vue'
import CameraTile from '../tiles/CameraTile.vue'
import PlainTile from '../tiles/PlainTile.vue'
import ClimateTile from '../tiles/ClimateTile.vue'
import SortView from '../SortView.vue'

const props = defineProps<{ room: Room }>()
defineEmits<{ back: [] }>()
const editing = ref(false)

const order = ['media', 'light', 'cover', 'lock', 'fan', 'switch', 'vacuum', 'climate', 'camera', 'motion', 'contact', 'sensor']
const devices = computed(() => [...props.room.devices].sort((a, b) => order.indexOf(cap(a)) - order.indexOf(cap(b))))
const tile = (c: string) => c === 'light' ? LightTile : c === 'media' ? MediaTile : c === 'camera' ? CameraTile : c === 'climate' ? ClimateTile : PlainTile
</script>

<template>
  <SortView v-if="room.id === 'unassigned'" :room="room" @back="$emit('back')" />
  <SortView v-else-if="editing" :room="room" editing @back="editing = false" />
  <section class="room" v-else>
    <header class="stage-head room-head">
      <button class="back" @click="$emit('back')" aria-label="Back to home"><Icon name="back" :size="22" /></button>
      <div>
        <h1 class="display">{{ room.name }}</h1>
        <p class="lede">{{ activity(room) }}</p>
      </div>
      <button class="back room-edit" @click="editing = true" aria-label="Edit this room" title="Rename or move things"><Icon name="edit" :size="20" /></button>
    </header>

    <SceneBar :room="room" />

    <div class="tiles" v-if="devices.length">
      <component v-for="d in devices" :key="d.id" :is="tile(cap(d))" :device="d" />
    </div>
    <div v-else class="empty-room">
      <p class="empty">Nothing in this room yet.</p>
      <p class="empty-sub">Devices you add to the {{ room.name }} will show up here on their own.</p>
    </div>
  </section>
</template>
