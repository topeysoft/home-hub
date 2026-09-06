<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, start, halt, load, visibleRooms, activity, roomActive, houseLine, weatherLine } from './store'
import Sky from './Sky.vue'
import HomeView from './views/HomeView.vue'
import RoomView from './views/RoomView.vue'
import Viewer from './Viewer.vue'
import LocationSheet from './LocationSheet.vue'
import Icon from './Icon.vue'

const now = ref(new Date())
const selected = ref<string | null>(new URLSearchParams(location.search).get('room') ?? safeGet('room'))   // ?room=kitchen deep-links a kiosk
function safeGet(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function open(id: string | null) { selected.value = id; try { id ? localStorage.setItem('room', id) : localStorage.removeItem('room') } catch {} }

const rooms = computed(visibleRooms)
const room = computed(() => rooms.value.find(r => r.id === selected.value) ?? null)

const hour = computed(() => now.value.getHours())
const ambient = computed(() => store.sky.elevation < -8 ? 'night' : store.sky.elevation < 6 ? (store.sky.azimuth < 180 ? 'dawn' : 'dusk') : 'day')
const weather = computed(weatherLine)
const WX_ICON: Record<string, string> = { sunny: 'sun', 'clear-night': 'moon', partlycloudy: 'cloud', cloudy: 'cloud', fog: 'fog', rainy: 'rain', pouring: 'rain', hail: 'rain', lightning: 'bolt', 'lightning-rainy': 'bolt', snowy: 'snow', 'snowy-rainy': 'snow', windy: 'wind', 'windy-variant': 'wind', exceptional: 'cloud' }
const wxIcon = computed(() => WX_ICON[store.sky.condition] ?? 'cloud')

const clock = computed(() => now.value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
const day = computed(() => now.value.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))

/* The wall panel rests after a few minutes: a clock, the date, one line about the house. A touch brings it back to Home. */
const IDLE_AFTER = 3 * 60 * 1000
const idle = ref(new URLSearchParams(location.search).get('rest') === '1')   // ?rest=1 previews the resting screen
let lastTouch = Date.now()
const kiosk = window.matchMedia('(min-width: 861px)')
function touched() {
  lastTouch = Date.now()
  if (idle.value) { idle.value = false; open(null) }
}
function checkIdle() { if (!idle.value && kiosk.matches && !store.viewer && !store.sheet && Date.now() - lastTouch > IDLE_AFTER) idle.value = true }

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
  <div class="shell" :data-ambient="ambient" :class="{ resting: idle }">
    <Sky />
    <div class="sky-veil"></div>
    <aside class="rail">
      <div class="rail-clock">
        <div class="rail-time">{{ clock }}</div>
        <div class="rail-day">{{ day }}</div>
        <div class="rail-weather" v-if="weather"><Icon :name="wxIcon" :size="16" /><span>{{ weather }}</span></div>
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
    <Transition name="sheet"><LocationSheet v-if="store.sheet === 'location'" /></Transition>

    <Transition name="toast">
      <div class="toast" :class="store.toast.kind" v-if="store.toast" :key="store.toast.id" role="status">{{ store.toast.text }}</div>
    </Transition>

    <Transition name="idle">
      <div class="idle" v-if="idle" aria-label="Tap to wake">
        <div class="idle-time display">{{ clock }}</div>
        <div class="idle-day">{{ day }}</div>
        <div class="idle-weather" v-if="weather"><Icon :name="wxIcon" :size="22" /><span>{{ weather }}</span></div>
        <div class="idle-line">{{ houseLine() }}</div>
      </div>
    </Transition>
  </div>
</template>
