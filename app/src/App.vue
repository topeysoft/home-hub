<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { getHome, connect, setIntent, type Home, type Room, type Device } from './api'
import DeviceTile from './DeviceTile.vue'

const home = reactive<Home>({ rooms: [] })
const linkUp = ref(false)
const error = ref('')
const now = ref(new Date())
const selected = ref<string>(safeGet('room') ?? '')

const rooms = computed(() => home.rooms.filter(r => r.id !== 'unassigned' || r.devices.length))
const room = computed<Room | undefined>(() => rooms.value.find(r => r.id === selected.value) ?? rooms.value.find(r => r.devices.length) ?? rooms.value[0])

function safeGet(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function pick(id: string) { selected.value = id; try { localStorage.setItem('room', id) } catch {} }

function applyHome(h: Home) { home.rooms = h.rooms }
function applyDevice(d: Device) {
  for (const r of home.rooms) {
    const i = r.devices.findIndex(x => x.id === d.id)
    if (i >= 0) { r.devices[i] = d; return }
  }
}

const ALL_INTENTS = [
  { id: 'occupied', label: 'Here', needs: ['light', 'media', 'switch', 'fan'] },
  { id: 'movie', label: 'Movie', needs: ['media'] },
  { id: 'asleep', label: 'Sleep', needs: ['light', 'media'] },
  { id: 'empty', label: 'Empty', needs: ['light', 'media', 'switch', 'fan'] },
]
// Only offer intents the room can act on: a room of cameras has nothing to put to sleep.
const intents = computed(() => {
  const caps = new Set((room.value?.devices ?? []).map(d => d.capability.split('.')[0]))
  return ALL_INTENTS.filter(i => i.needs.some(c => caps.has(c)))
})
async function intent(id: string) {
  if (!room.value) return
  try { await setIntent(room.value.id, id); room.value.intent = id; error.value = '' }
  catch (e: any) { error.value = e.message }
}

let stop: (() => void) | undefined, tick: number | undefined
onMounted(async () => {
  try { applyHome(await getHome()) } catch (e: any) { error.value = 'Brain unreachable' }
  stop = connect({ device: applyDevice, home: applyHome, link: v => (linkUp.value = v) })
  tick = window.setInterval(() => (now.value = new Date()), 15000)
})
onUnmounted(() => { stop?.(); clearInterval(tick) })

const clock = computed(() => now.value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
const day = computed(() => now.value.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))
const summary = computed(() => {
  if (!room.value) return ''
  const on = room.value.devices.filter(d => ['on', 'playing', 'open', 'unlocked'].includes(d.state)).length
  return on ? `${on} active` : 'all quiet'
})
</script>

<template>
  <div class="panel">
    <header class="top">
      <div class="clock"><span class="time">{{ clock }}</span><span class="day">{{ day }}</span></div>
      <div class="link" :class="{ up: linkUp }">{{ linkUp ? 'live' : 'reconnecting' }}</div>
    </header>

    <nav class="rooms">
      <button v-for="r in rooms" :key="r.id" class="room-tab" :class="{ active: r.id === room?.id }" @click="pick(r.id)">
        {{ r.name }}<span class="count" v-if="r.devices.length">{{ r.devices.length }}</span>
      </button>
    </nav>

    <main v-if="room" class="room">
      <div class="room-head">
        <h1>{{ room.name }}</h1>
        <span class="summary">{{ summary }}</span>
      </div>
      <div class="intents" v-if="intents.length">
        <button v-for="i in intents" :key="i.id" class="intent" :class="{ active: room.intent === i.id }" @click="intent(i.id)">{{ i.label }}</button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="grid" v-if="room.devices.length">
        <DeviceTile v-for="d in room.devices" :key="d.id" :device="d" @error="error = $event" />
      </div>
      <p v-else class="empty">Nothing in this room yet.</p>
    </main>
    <main v-else class="room"><p class="empty">{{ error || 'Loading the house…' }}</p></main>
  </div>
</template>
