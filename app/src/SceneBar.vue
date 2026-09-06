<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Room } from './api'
import { capsOf, currentScene, runScene, scenesFor, store, type Scene } from './store'
import Icon from './Icon.vue'

const props = defineProps<{ room: Room | null }>()
const scenes = computed(() => scenesFor(props.room))
const caps = computed(() => capsOf(props.room ? props.room.devices : store.rooms.flatMap(r => r.devices)))
const current = computed(() => props.room ? currentScene(props.room) : null)   // highlighted only while the room still matches it
const busy = ref(''), done = ref('')
async function choose(s: Scene) {
  if (busy.value) return
  busy.value = s.id
  const ok = await runScene(props.room, s)
  busy.value = ''
  if (ok) { done.value = s.id; setTimeout(() => (done.value = ''), 1800) }
}
</script>

<template>
  <div class="scenes" v-if="scenes.length" role="group" :aria-label="room ? 'Room scenes' : 'House scenes'">
    <button v-for="s in scenes" :key="s.id" class="scene" :class="{ active: current === s.id, busy: busy === s.id, done: done === s.id }" @click="choose(s)">
      <span class="scene-icon"><Icon :name="done === s.id ? 'check' : s.icon" :size="20" /></span>
      <span class="scene-text">
        <span class="scene-label">{{ s.label }}</span>
        <span class="scene-hint">{{ busy === s.id ? 'One moment…' : s.hint(caps) }}</span>
      </span>
    </button>
  </div>
</template>
