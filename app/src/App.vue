<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, start, halt, visibleRooms, activity, roomActive } from './store'
import HomeView from './views/HomeView.vue'
import RoomView from './views/RoomView.vue'
import Icon from './Icon.vue'

const now = ref(new Date())
const selected = ref<string | null>(safeGet('room'))
function safeGet(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function open(id: string | null) { selected.value = id; try { id ? localStorage.setItem('room', id) : localStorage.removeItem('room') } catch {} }

const rooms = computed(visibleRooms)
const room = computed(() => rooms.value.find(r => r.id === selected.value) ?? null)

const hour = computed(() => now.value.getHours())
const ambient = computed(() => hour.value < 5 ? 'night' : hour.value < 10 ? 'dawn' : hour.value < 17 ? 'day' : hour.value < 21 ? 'dusk' : 'night')
const clock = computed(() => now.value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
const day = computed(() => now.value.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))

let tick: number | undefined
onMounted(() => { start(); tick = window.setInterval(() => (now.value = new Date()), 10000) })
onUnmounted(() => { halt(); clearInterval(tick) })
</script>

<template>
  <div class="shell" :data-ambient="ambient">
    <aside class="rail">
      <div class="rail-clock">
        <div class="rail-time">{{ clock }}</div>
        <div class="rail-day">{{ day }}</div>
      </div>
      <nav class="rail-nav">
        <button class="rail-item" :class="{ active: !room }" @click="open(null)">
          <Icon name="home" :size="20" /><span>Home</span>
        </button>
        <div class="rail-label">Rooms</div>
        <button v-for="r in rooms" :key="r.id" class="rail-item" :class="{ active: room?.id === r.id }" @click="open(r.id)">
          <span class="dot" :class="{ on: roomActive(r) }"></span>
          <span class="rail-name">{{ r.name }}</span>
          <span class="rail-sub">{{ activity(r) }}</span>
        </button>
      </nav>
      <div class="rail-foot">
        <span class="link" :class="{ up: store.linkUp }">{{ store.linkUp ? 'Connected' : 'Reconnecting' }}</span>
      </div>
    </aside>

    <main class="stage">
      <Transition name="view" mode="out-in">
        <RoomView v-if="room" :key="room.id" :room="room" @back="open(null)" />
        <HomeView v-else key="home" :rooms="rooms" :hour="hour" @open="open" />
      </Transition>
    </main>
  </div>
</template>
