<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, start, halt, load, visibleRooms, activity, roomActive, houseLine, weatherLine, needsSetup, dismissToast } from './store'
import Setup from './Setup.vue'
import Join from './Join.vue'
import AddSheet from './AddSheet.vue'
import CodeSheet from './CodeSheet.vue'
import CodePrompt from './CodePrompt.vue'
import { lock } from './code'
import Sky from './Sky.vue'
import HomeView from './views/HomeView.vue'
import RoomView from './views/RoomView.vue'
import Viewer from './Viewer.vue'
import LocationSheet from './LocationSheet.vue'
import WhySheet from './WhySheet.vue'
import RoutinesSheet from './RoutinesSheet.vue'
import HubSheet from './HubSheet.vue'
import LookSheet from './LookSheet.vue'
import Icon from './Icon.vue'
import { upcomingLine } from './upcoming'
import { isTone, toneVars, type ToneName } from './tone'
import { isLayout, type LayoutName } from './layout'
import RailView from './views/RailView.vue'

const now = ref(new Date())
const selected = ref<string | null>(new URLSearchParams(location.search).get('room') ?? safeGet('room'))   // ?room=kitchen deep-links a kiosk
function safeGet(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function open(id: string | null) { selected.value = id; try { id ? localStorage.setItem('room', id) : localStorage.removeItem('room') } catch {} }

const rooms = computed(visibleRooms)
/* the rail keeps the current room in view: on a wall it scrolls the list, on a phone the chip strip */
watch(selected, () => nextTick(() => document.querySelector('.rail-item.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })))
const setup = computed(() => !!store.status && (store.previewSetup || needsSetup()))
const room = computed(() => rooms.value.find(r => r.id === selected.value) ?? null)

const ambient = computed(() => store.sky.elevation < -8 ? 'night' : store.sky.elevation < 6 ? (store.sky.azimuth < 180 ? 'dawn' : 'dusk') : 'day')

/* How the panel looks is the house's answer, not this screen's: it arrives with
   the ambient and changes on every panel at once when someone picks another.
   ?tone= and ?layout= override it for this tab only, the way ?at= and ?wx= do,
   so previewing a look never changes what the rest of the house is showing. */
const params = new URLSearchParams(location.search)
const toneParam = params.get('tone'), layoutParam = params.get('layout')
const toneName = computed<ToneName>(() => isTone(toneParam) ? toneParam : (isTone(store.ambient.look?.tone) ? store.ambient.look!.tone as ToneName : 'follow'))
const tone = computed(() => toneVars(store.sky.elevation, store.sky.condition, toneName.value))
const layout = computed<LayoutName>(() => isLayout(layoutParam) ? layoutParam : (isLayout(store.ambient.look?.layout) ? store.ambient.look!.layout as LayoutName : 'stack'))
const weather = computed(weatherLine)
const WX_ICON: Record<string, string> = { sunny: 'sun', 'clear-night': 'moon', partlycloudy: 'cloud', cloudy: 'cloud', fog: 'fog', rainy: 'rain', pouring: 'rain', hail: 'rain', lightning: 'bolt', 'lightning-rainy': 'bolt', snowy: 'snow', 'snowy-rainy': 'snow', windy: 'wind', 'windy-variant': 'wind', exceptional: 'cloud' }
const wxIcon = computed(() => WX_ICON[store.sky.condition] ?? 'cloud')

const previewAt = new URLSearchParams(location.search).get('at')   // ?at=19:30 previews an hour; the clock follows the sky so a preview agrees with itself
const shown = computed(() => { if (!previewAt) return now.value; const d = new Date(now.value); const [h, m] = previewAt.split(':').map(Number); d.setHours(h || 0, m || 0, 0, 0); return d })
const clock = computed(() => shown.value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
const nextLine = computed(() => idle.value ? upcomingLine(shown.value) : '')   // only worked out while the panel rests
const day = computed(() => shown.value.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))

/* The wall panel rests after a few minutes: a clock, the date, one line about the house. A touch brings it back to Home. */
const IDLE_AFTER = 3 * 60 * 1000
const idle = ref(new URLSearchParams(location.search).get('rest') === '1')   // ?rest=1 previews the resting screen
let lastTouch = Date.now()
const kiosk = window.matchMedia('(min-width: 861px)')
function touched() {
  lastTouch = Date.now()
  if (idle.value) { idle.value = false; open(null) }
}
watch(() => store.asks.length, (n, o) => { if (n > o) touched() })   // a phone knocking wakes the wall so the card is seen
async function rejoin() { halt(); await start() }                       // this screen just joined: read the house and reconnect
function checkIdle() { if (!idle.value && kiosk.matches && !store.viewer && !store.sheet && !setup.value && Date.now() - lastTouch > IDLE_AFTER) idle.value = true }

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
  <div class="shell" :data-ambient="ambient" :style="tone" :class="{ resting: idle, 'in-setup': setup || lock.unpaired }">
    <Sky :quiet="!idle && !setup" />
    <div class="sky-veil"></div>
    <Join v-if="lock.unpaired" @joined="rejoin" />
    <Setup v-else-if="setup" />
    <aside class="rail" v-if="!setup && !lock.unpaired">
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
        <button v-for="r in rooms" :key="r.id" class="rail-item" :class="{ active: room?.id === r.id, attention: r.id === 'unassigned' }" @click="open(r.id)">
          <span class="dot" :class="{ on: roomActive(r) }"></span>
          <span class="rail-name">{{ r.name }}</span>
          <span class="rail-sub">{{ activity(r) }}</span>
        </button>
      </nav>
      <div class="rail-tail">
        <button class="rail-item rail-add" :class="{ attention: store.found.length }" @click="store.sheet = 'add'">
          <Icon name="plus" :size="16" /><span class="rail-name">Add a device</span>
          <span class="rail-sub" v-if="store.found.length">{{ store.found.length }} found nearby</span>
        </button>
      </div>
      <div class="rail-foot">
        <span class="link" :class="{ up: store.linkUp }">{{ store.linkUp ? 'Connected' : 'Reconnecting' }}</span>
      </div>
    </aside>

    <main class="stage" v-if="!setup && !lock.unpaired">
      <Transition name="banner">
        <div class="banner" v-if="store.loaded && store.linkLost"><Icon name="refresh" :size="16" /> Reconnecting to the hub. What you see may be a little behind.</div>
      </Transition>

      <div class="offline" v-if="!store.loaded || store.status?.driver !== 'ready'">
        <template v-if="store.loaded && store.status && store.status.driver !== 'ready'">
          <span class="offline-icon pulse"><Icon name="home" :size="28" /></span>
          <h1 class="display">{{ store.restoring ? 'Restoring your house' : store.updating ? 'Updating the hub' : store.status.driver === 'down' ? 'The engine is starting' : 'Reconnecting' }}</h1>
          <p>{{ store.restoring || store.updating ? 'A few minutes. The lights and switches keep working; this screen comes back on its own.' : store.status.reason || 'The house will be back in a moment. Nothing needs doing.' }}</p>
        </template>
        <template v-else-if="store.error">
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
        <RoomView v-if="room" :key="room.id" :room="room" @back="open(null)" @open="open" />
        <RailView v-else-if="layout === 'rail'" key="home-rail" :rooms="rooms" :now="shown" @open="open" />
        <HomeView v-else key="home-stack" :rooms="rooms" :now="shown" @open="open" />
      </Transition>
    </main>

    <Viewer />
    <Transition name="sheet"><LocationSheet v-if="store.sheet === 'location'" /></Transition>
    <Transition name="sheet"><AddSheet v-if="store.sheet === 'add'" /></Transition>
    <Transition name="sheet"><CodeSheet v-if="store.sheet === 'code'" /></Transition>
    <Transition name="sheet"><WhySheet v-if="store.sheet === 'why'" /></Transition>
    <Transition name="sheet"><RoutinesSheet v-if="store.sheet === 'routines'" /></Transition>
    <Transition name="sheet"><HubSheet v-if="store.sheet === 'hub'" /></Transition>
    <Transition name="sheet"><LookSheet v-if="store.sheet === 'look'" /></Transition>
    <Transition name="sheet"><CodePrompt v-if="lock.prompt" /></Transition>

    <Transition name="toast">
      <div class="toast" :class="store.toast.kind" v-if="store.toast" :key="store.toast.id" role="status">
        <span class="toast-text">{{ store.toast.text }}</span>
        <button class="toast-act" v-if="store.toast.action" @click="store.toast.action.run(); dismissToast()">{{ store.toast.action.label }}</button>
      </div>
    </Transition>

    <Transition name="idle">
      <div class="idle" v-if="idle" aria-label="Tap to wake">
        <div class="idle-time display">{{ clock }}</div>
        <div class="idle-day">{{ day }}</div>
        <div class="idle-weather" v-if="weather"><Icon :name="wxIcon" :size="22" /><span>{{ weather }}</span></div>
        <div class="idle-line">{{ houseLine() }}</div>
        <div class="idle-next" v-if="nextLine">{{ nextLine }}</div>
      </div>
    </Transition>
  </div>
</template>
