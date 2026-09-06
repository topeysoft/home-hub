<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, activity, roomActive, cap, houseLine, describe, ago, refreshEvents } from '../store'
import type { Room } from '../api'
import Icon from '../Icon.vue'
import SceneBar from '../SceneBar.vue'
import CameraTile from '../tiles/CameraTile.vue'

const props = defineProps<{ rooms: Room[]; hour: number }>()
defineEmits<{ open: [id: string] }>()

const greeting = computed(() => props.hour < 5 ? 'Good night' : props.hour < 12 ? 'Good morning' : props.hour < 17 ? 'Good afternoon' : props.hour < 21 ? 'Good evening' : 'Good night')
const line = computed(houseLine)
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))
/* the one number worth a glance on a room card: its temperature, when a sensor in the room reads one */
function temp(r: Room): string {
  const d = r.devices.find(d => d.capability === 'sensor.temperature' && Number.isFinite(Number(d.state)))
  return d ? `${Math.round(Number(d.state))}°` : ''
}

const routinesLine = computed(() => {
  const n = store.routines.length, off = store.routines.filter(r => r.enabled === false).length
  return `${n === 1 ? '1 routine' : `${n} routines`}${off ? `, ${off} off` : ''}`
})

const now = ref(Date.now())
const recent = computed(() => {
  const out: { key: number; text: string; icon: string; when: string }[] = []
  let last = ''
  for (const ev of store.events) {
    const d = describe(ev); if (!d || d.text === last) continue
    last = d.text; out.push({ key: ev.ts, text: d.text, icon: d.icon, when: ago(ev.ts, now.value) })
    if (out.length >= 6) break
  }
  return out
})
let t1: number | undefined, t2: number | undefined
onMounted(() => { refreshEvents(); t1 = window.setInterval(refreshEvents, 30000); t2 = window.setInterval(() => (now.value = Date.now()), 20000) })
onUnmounted(() => { clearInterval(t1); clearInterval(t2) })
</script>

<template>
  <section class="home">
    <header class="stage-head home-head">
      <div>
        <h1 class="display">{{ greeting }}</h1>
        <p class="lede">{{ line }}</p>
      </div>
      <SceneBar :room="null" />
    </header>

    <button class="nudge" v-if="store.found.length" @click="store.sheet = 'add'">
      <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
      <span class="nudge-text"><span class="nudge-title">{{ store.found.length === 1 ? `Found ${store.found[0].title}` : `Found ${store.found.length} new things nearby` }}</span><span class="nudge-sub">{{ store.found.length === 1 ? 'Tap to add it to the house.' : store.found.slice(0, 3).map(f => f.title).join(', ') + (store.found.length > 3 ? '…' : '') }}</span></span>
    </button>
    <button class="nudge" v-if="store.status?.setup_done && store.status.locked === false" @click="store.sheet = 'code'">
      <span class="nudge-icon"><Icon name="lock" :size="20" /></span>
      <span class="nudge-text"><span class="nudge-title">Lock the settings</span><span class="nudge-sub">Anyone on the Wi‑Fi can change the house right now. A code keeps the controls open and the settings yours.</span></span>
    </button>
    <button class="nudge" v-if="store.ambientLoaded && !store.ambient.location" @click="store.sheet = 'location'">
      <span class="nudge-icon"><Icon name="pin" :size="20" /></span>
      <span class="nudge-text"><span class="nudge-title">Where is home?</span><span class="nudge-sub">Set a location once and the sky, sunrise and weather will follow it.</span></span>
    </button>

    <div class="block">
      <h2 class="label">Rooms</h2>
      <div class="room-grid">
        <button v-for="r in rooms" :key="r.id" class="room-card" :class="{ active: roomActive(r), empty: !r.devices.length }" @click="$emit('open', r.id)">
          <div class="room-card-top">
            <span class="room-temp" v-if="temp(r)"><Icon name="sensor" :size="14" />{{ temp(r) }}</span>
          </div>
          <div class="room-card-name display">{{ r.name }}</div>
          <div class="room-card-activity">{{ activity(r) }}</div>
        </button>
      </div>
    </div>

    <div class="block" v-if="cameras.length">
      <h2 class="label">Cameras</h2>
      <div class="camera-row">
        <CameraTile v-for="c in cameras" :key="c.id" :device="c" compact />
      </div>
    </div>

    <div class="block" v-if="recent.length">
      <h2 class="label">Recently</h2>
      <ul class="recent">
        <li v-for="e in recent" :key="e.key">
          <span class="recent-icon"><Icon :name="e.icon" :size="16" /></span>
          <span class="recent-text">{{ e.text }}</span>
          <span class="recent-when">{{ e.when }}</span>
        </li>
      </ul>
    </div>
    <footer class="home-foot" v-if="store.ambient.location || store.routines.length">
      <button class="home-place" v-if="store.ambient.location" @click="store.sheet = 'location'"><Icon name="pin" :size="14" /> {{ store.ambient.location.name }}<span class="home-change">Change</span></button>
      <button class="home-place" v-if="store.routines.length" @click="store.sheet = 'routines'"><Icon name="sparkle" :size="14" /> {{ routinesLine }}<span class="home-change">See</span></button>
    </footer>
  </section>
</template>
