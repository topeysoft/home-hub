<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, start, halt, load, visibleRooms, activity, roomActive, houseLine } from './store'
import HomeView from './views/HomeView.vue'
import RoomView from './views/RoomView.vue'
import Viewer from './Viewer.vue'
import Icon from './Icon.vue'

const now = ref(new Date())
const selected = ref<string | null>(new URLSearchParams(location.search).get('room') ?? safeGet('room'))   // ?room=kitchen deep-links a kiosk
function safeGet(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function open(id: string | null) { selected.value = id; try { id ? localStorage.setItem('room', id) : localStorage.removeItem('room') } catch {} }

const rooms = computed(visibleRooms)
const room = computed(() => rooms.value.find(r => r.id === selected.value) ?? null)

const hour = computed(() => now.value.getHours())
const ambient = computed(() => hour.value < 5 ? 'night' : hour.value < 10 ? 'dawn' : hour.value < 17 ? 'day' : hour.value < 21 ? 'dusk' : 'night')
const clock = computed(() => now.value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
const day = computed(() => now.value.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))

/* The wall panel rests after a few minutes: a clock, the date, one line about the house. A touch brings it back to Home. */
const IDLE_AFTER = 3 * 60 * 1000
const idle = ref(false)
let lastTouch = Date.now()
const kiosk = window.matchMedia('(min-width: 861px)')
function touched() {
  lastTouch = Date.now()
  if (idle.value) { idle.value = false; open(null) }
}
function checkIdle() { if (!idle.value && kiosk.matches && !store.viewer && Date.now() - lastTouch > IDLE_AFTER) idle.value = true }

let tick: number | undefined, idler: number | undefined
onMounted(() => {
  start()
  tick = window.setInterval(() => (now.value = new Date()), 10000)
  idler = window.setInterval(checkIdle, 5000)
  window.addEventListener('pointerdown', touched, { capture: true })
  window.addEventListener('keydown', touched, { capture: true })
})
onUnmounted(() => {
  halt(); clearInterval(tick); clearInterval(idler)
  window.removeEventListener('pointerdown', touched, { capture: true })
  window.removeEventListener('keydown', touched, { capture: true })
})
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
      <Transition name="banner">
        <div class="banner" v-if="store.loaded && store.linkLost"><Icon name="refresh" :size="16" /> Reconnecting to the hub. What you see may be a little behind.</div>
      </Transition>

      <div class="offline" v-if="!store.loaded">
        <template v-if="store.error">
          <span class="offline-icon"><Icon name="home" :size="28" /></span>
          <h1 class="display">Can't reach the hub</h1>
          <p>Make sure the hub is powered on and this screen is on the same network. It will reconnect on its own.</p>
          <button class="button" @click="load()"><Icon name="refresh" :size="18" /> Try again</button>
        </template>
        <template v-else>
          <span class="offline-icon pulse"><Icon name="home" :size="28" /></span>
          <p class="empty">Finding the house…</p>
        </template>
      </div>
      <Transition v-else name="view" mode="out-in">
        <RoomView v-if="room" :key="room.id" :room="room" @back="open(null)" />
        <HomeView v-else key="home" :rooms="rooms" :hour="hour" @open="open" />
      </Transition>
    </main>

    <Viewer />

    <Transition name="toast">
      <div class="toast" :class="store.toast.kind" v-if="store.toast" :key="store.toast.id" role="status">{{ store.toast.text }}</div>
    </Transition>

    <Transition name="idle">
      <div class="idle" v-if="idle" aria-label="Tap to wake">
        <div class="idle-time display">{{ clock }}</div>
        <div class="idle-day">{{ day }}</div>
        <div class="idle-line">{{ houseLine() }}</div>
      </div>
    </Transition>
  </div>
</template>
