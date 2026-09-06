<script setup lang="ts">
import { computed, ref } from 'vue'
import { activity, cap } from '../store'
import { setIntent, type Room } from '../api'
import Icon from '../Icon.vue'
import LightTile from '../tiles/LightTile.vue'
import MediaTile from '../tiles/MediaTile.vue'
import CameraTile from '../tiles/CameraTile.vue'
import PlainTile from '../tiles/PlainTile.vue'

const props = defineProps<{ room: Room }>()
defineEmits<{ back: [] }>()
const error = ref('')

const ALL = [
  { id: 'occupied', label: 'Here', needs: ['light', 'media', 'switch', 'fan'] },
  { id: 'movie', label: 'Movie', needs: ['media'] },
  { id: 'asleep', label: 'Sleep', needs: ['light', 'media'] },
  { id: 'empty', label: 'Empty', needs: ['light', 'media', 'switch', 'fan'] },
]
const caps = computed(() => new Set(props.room.devices.map(cap)))
const intents = computed(() => ALL.filter(i => i.needs.some(c => caps.value.has(c))))
const busy = ref('')
async function choose(id: string) {
  busy.value = id
  try { await setIntent(props.room.id, id); props.room.intent = id; error.value = '' }
  catch (e: any) { error.value = e.message }
  finally { busy.value = '' }
}

const order = ['media', 'light', 'cover', 'lock', 'fan', 'switch', 'camera', 'vacuum', 'motion', 'contact', 'sensor']
const devices = computed(() => [...props.room.devices].sort((a, b) => order.indexOf(cap(a)) - order.indexOf(cap(b))))
const tile = (c: string) => c === 'light' ? LightTile : c === 'media' ? MediaTile : c === 'camera' ? CameraTile : PlainTile
</script>

<template>
  <section class="room">
    <header class="stage-head room-head">
      <button class="back" @click="$emit('back')" aria-label="Back to home"><Icon name="back" :size="22" /></button>
      <div>
        <h1 class="display">{{ room.name }}</h1>
        <p class="lede">{{ activity(room) }}</p>
      </div>
    </header>

    <div class="scenes" v-if="intents.length" role="group" aria-label="Room mode">
      <button v-for="i in intents" :key="i.id" class="scene" :class="{ active: room.intent === i.id, busy: busy === i.id }" @click="choose(i.id)">{{ i.label }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="tiles" v-if="devices.length">
      <component v-for="d in devices" :key="d.id" :is="tile(cap(d))" :device="d" @error="error = $event" />
    </div>
    <p v-else class="empty">Nothing in this room yet. Devices you add will appear here on their own.</p>
  </section>
</template>
