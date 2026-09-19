<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, start, halt, load, visibleRooms, activity, roomActive, houseLine, weatherLine, needsSetup, dismissToast, updateReady, forgetDone, cap } from './store'
import Setup from './Setup.vue'
import Join from './Join.vue'
import Away from './Away.vue'
import CodePrompt from './CodePrompt.vue'
import { lock } from './code'
import Sky from './Sky.vue'
import ArtDefs from './ArtDefs.vue'
import HomeView from './views/HomeView.vue'
import RoomView from './views/RoomView.vue'
import Viewer from './Viewer.vue'
import WhySheet from './WhySheet.vue'
import BridgeSheet from './BridgeSheet.vue'
import HousePanel from './HousePanel.vue'
import AskPane from './AskPane.vue'
import { isPage } from './pages'
import Opened from './Opened.vue'
import WeatherPane from './WeatherPane.vue'
import Icon from './Icon.vue'
import { upcomingLine } from './upcoming'
import { glassVars, isTone, toneVars, type ToneName } from './tone'
import { isFace, isLayout, isNav, type FaceName, type LayoutName, type NavName } from './layout'
import { feelFrom, placeOf, TOUCHED_AT, READ_AT } from './look'
import RailView from './views/RailView.vue'
import WallView from './views/WallView.vue'
import RoomsView from './views/RoomsView.vue'
import CamerasView from './views/CamerasView.vue'
import TopBar from './TopBar.vue'
import Household from './Household.vue'

const now = ref(new Date())
const selected = ref<string | null>(new URLSearchParams(location.search).get('room') ?? safeGet('room'))   // ?room=kitchen deep-links a kiosk
function safeGet(k: string) { try { return localStorage.getItem(k) } catch { return null } }
function open(id: string | null) { selected.value = id; try { id ? localStorage.setItem('room', id) : localStorage.removeItem('room') } catch {} }

const rooms = computed(visibleRooms)
/* the rail keeps the current room in view: on a wall it scrolls the list, on a phone the chip strip */
watch(selected, () => nextTick(() => document.querySelector('.rail-item.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })))
const setup = computed(() => !!store.status && (store.previewSetup || needsSetup()))
/* The house is not showing: either this phone is not in it yet, or it is being reached from outside and
   the house did not open. Both put a screen of their own up in place of everything. */
const shut = computed(() => lock.unpaired || !!lock.away)
const panel = computed(() => isPage(store.sheet))   // This house is open, on one of its pages
/* A phone at the door opens its own pane, and stays open until it is answered or put aside. It is
   not `store.opened` -- that is a device -- but it is the same surface and the room recedes behind
   it the same way, so it counts towards the shell's opened state. */
/* A phone that was at the door before this screen went away is not at the door now: the ask pane sits
   outside the guards below, so it is this computed that has to know the house is not showing. */
const asking = computed(() => !shut.value && store.asks.length > 0 && !store.askAside)
const room = computed(() => rooms.value.find(r => r.id === selected.value) ?? null)

const ambient = computed(() => store.sky.elevation < -8 ? 'night' : store.sky.elevation < 6 ? (store.sky.azimuth < 180 ? 'dawn' : 'dusk') : 'day')

/* How the panel looks is the house's answer, not this screen's: it arrives with
   the ambient and changes on every panel at once when someone picks another.
   ?tone= and ?layout= override it for this tab only, the way ?at= and ?wx= do,
   so previewing a look never changes what the rest of the house is showing. */
const params = new URLSearchParams(location.search)
const toneParam = params.get('tone'), layoutParam = params.get('layout')

/* The house's feel, which is what the Look page actually writes: one of three,
   and it supplies the face and the tone unless somebody has been under
   Customize and set one by hand. Falls back to Calm, so a hub that has never
   been asked and an old one that has no feel stored both land somewhere real. */
const feel = computed(() => feelFrom(store.ambient.look))

/* Where this screen is. The ONE thing here that is the screen's answer rather
   than the house's, and only because it is not a preference: a phone is a phone.
   Bound to the two seams look.ts names so it re-reads on a rotate or a resize
   rather than being sampled once at boot -- a tablet turned on its side is a
   different room to arrange for. */
const atTouch = window.matchMedia(`(min-width: ${TOUCHED_AT}px)`)
const atRead = window.matchMedia(`(min-width: ${READ_AT}px)`)
const width = ref(window.innerWidth)
const measure = () => (width.value = window.innerWidth)
const place = computed(() => placeOf(width.value))

const toneName = computed<ToneName>(() => isTone(toneParam) ? toneParam : (isTone(store.ambient.look?.tone) ? store.ambient.look!.tone as ToneName : feel.value.tone))
const tone = computed(() => toneVars(store.sky.elevation, store.sky.condition, toneName.value))
const layout = computed<LayoutName>(() => isLayout(layoutParam) ? layoutParam : (isLayout(store.ambient.look?.layout) ? store.ambient.look!.layout as LayoutName : place.value.layout))

/* where the way around the house lives -- the side list, or tabs across the
   top -- is the house's choice too; ?nav=top previews it. The tab is this
   screen's own, like the room it is in. */
/* what the panel is made of: paper, or glass. The house's answer like the rest,
   and ?face=glass previews it for this tab alone. */
const faceParam = params.get('face')
const face = computed<FaceName>(() => isFace(faceParam) ? faceParam : (isFace(store.ambient.look?.face) ? store.ambient.look!.face as FaceName : feel.value.face))
/* the pane's own properties, derived from the same sky the tone is -- and from
   the tone itself, which it ignored until 17 Sep 2026, so that Warm and Cool
   and Pastel did nothing at all on this face. A face that is not on costs
   nothing, because there is nothing to bind. */
const glass = computed(() => face.value === 'glass'
  ? glassVars(store.sky.elevation, store.sky.condition, toneName.value) : {})
/* Whether this screen can paint a pane at all. Asked once: it cannot change
   while the panel is open, and a host that cannot blur gets the face flattened
   rather than taken away -- panel.css says what that means. ?flat=1 previews
   it, which is the only way anyone will ever see it on a machine that can. */
const flat = params.get('flat') === '1'
  || !(CSS.supports('backdrop-filter', 'blur(1px)') || CSS.supports('-webkit-backdrop-filter', 'blur(1px)'))

const navParam = params.get('nav')
const nav = computed<NavName>(() => isNav(navParam) ? navParam : (isNav(store.ambient.look?.nav) ? store.ambient.look!.nav as NavName : place.value.nav))
const tab = ref<'home' | 'rooms' | 'cameras'>('home')
function go(t: 'home' | 'rooms' | 'cameras') { tab.value = t; open(null) }

/* an opened device lends the room its color: a warm lamp pushes the field
   amber, a lock or a camera cools it. Falls back to the lamp, which is what a
   house at rest is lit by anyway. */
const openTint = computed(() => {
  const d = store.opened; if (!d) return {}
  const warm = ['light', 'media', 'switch', 'fan'].includes(cap(d))
  return { '--open-tint': `var(${warm ? '--tint-light' : '--tint-lock'}, rgba(233,184,114,.30))` }
})
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
const woke = ref(0)   // counted so Home can arrive again on every wake, not only on the first load
function touched() {
  lastTouch = Date.now()
  if (!idle.value) return
  idle.value = false
  /* Waking goes home, so what somebody left open before the panel rested goes with it. A phone
     asking to join is the exception and stays: that one is a question still waiting for an answer,
     not something left lying around. */
  store.opened = null
  store.outside = false
  open(null)
  woke.value++
}
/* A phone knocking wakes the wall, and clears anything put aside so the pane comes back up: this is
   the one event the panel turns the screen on for, and a knock that has been set aside must not
   silence the next one. */
watch(() => store.asks.length, (n, o) => { if (n > o) { store.askAside = false; touched() } })
async function rejoin() { halt(); await start() }                       // this screen just joined: read the house and reconnect
function checkIdle() {
  if (!idle.value && kiosk.matches && !store.viewer && !store.sheet && !setup.value && Date.now() - lastTouch > IDLE_AFTER) idle.value = true
  forgetDone(idle.value)   // and the stale ones either way, for a screen that never rests
}
/*
 * The panel has looked away, and that is the ONE moment Home may take back a
 * card you have just quieted: at rest, behind another app, or half an hour on.
 * Nobody is watching, so the row closes over the gap with nothing moving under a
 * finger -- which is the whole reason those cards stay in the first place. See
 * `done` in store.ts. Coming back from hidden does not sweep: a phone brought
 * out of a pocket is somebody looking again, and this already ran on the way in.
 */
function looked() { if (document.visibilityState === 'hidden') forgetDone(true) }

let tick: number | undefined, idler: number | undefined
onMounted(() => {
  start()
  tick = window.setInterval(() => (now.value = new Date()), 10000)
  idler = window.setInterval(checkIdle, 5000)
  window.addEventListener('pointerdown', touched, { capture: true })
  window.addEventListener('keydown', touched, { capture: true })
  document.addEventListener('visibilitychange', looked)
  atTouch.addEventListener('change', measure)
  atRead.addEventListener('change', measure)
})
onUnmounted(() => {
  halt(); clearInterval(tick); clearInterval(idler)
  window.removeEventListener('pointerdown', touched, { capture: true })
  window.removeEventListener('keydown', touched, { capture: true })
  document.removeEventListener('visibilitychange', looked)
  atTouch.removeEventListener('change', measure)
  atRead.removeEventListener('change', measure)
})
</script>

<template>
  <div class="shell" :data-ambient="ambient" :data-nav="nav" :data-face="face" :data-layout="layout" :data-flat="face === 'glass' && flat ? '' : null" :style="[tone, glass, openTint]" :class="{ resting: idle, 'in-setup': setup || shut, 'opened-shell': !!store.opened || store.outside || panel || asking }">
    <Sky :quiet="!idle && !setup" />
    <!-- glass lays its blooms on the sky the canvas just painted, under the veil -->
    <div class="sky-bloom" v-if="face === 'glass'"></div>
    <ArtDefs />
    <div class="sky-veil"></div>
    <Away v-if="lock.away" />
    <Join v-else-if="lock.unpaired" @joined="rejoin" />
    <Setup v-else-if="setup" />
    <TopBar v-if="!setup && !shut && nav === 'top'" :clock="clock" :day="day" :now="shown" :tab="tab" :in-room="!!room" @go="go" />
    <aside class="rail" v-if="!setup && !shut && nav === 'side'">
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
        <button class="rail-item rail-house" :class="{ attention: updateReady() }" @click="store.sheet = 'house'">
          <Icon name="menu" :size="16" /><span class="rail-name">This house</span>
          <span class="rail-sub" v-if="updateReady()">An update is ready</span>
        </button>
      </div>
      <div class="rail-foot">
        <span class="link" :class="{ up: store.linkUp }">{{ store.linkUp ? 'Connected' : 'Reconnecting' }}</span>
      </div>
    </aside>

    <main class="stage" v-if="!setup && !shut">
      <Transition name="banner">
        <div class="banner" v-if="store.loaded && store.linkLost"><Icon name="refresh" :size="16" /> Reconnecting to the hub. What you see may be a little behind.</div>
      </Transition>

      <div class="offline" v-if="!store.loaded || store.restarting || store.status?.driver !== 'ready'">
        <!-- A restart is the one thing this panel does that destroys the thing doing it, and it is
             short enough to count. So it gets the overlay from the moment it is asked for rather than
             when the hub next answers, and a number that runs out rather than a spinner: a spinner
             says "this may never end". The figure is the hub's own last restart at this rung. -->
        <template v-if="store.restarting">
          <span class="offline-icon pulse"><Icon name="refresh" :size="28" /></span>
          <h1 class="display">{{ store.restarting.rung === 'machine' ? 'Restarting the little computer' : store.restarting.rung === 'everything' ? 'Restarting everything' : 'Restarting the hub' }}</h1>
          <p>{{ store.restarting.left > 0 ? `Back in about ${store.restarting.left} seconds.` : 'Taking longer than usual. Still trying.' }}</p>
          <p class="keeps">{{ store.restarting.rung === 'hub' ? 'Lights and switches keep working.' : 'Switches on the wall keep working.' }}</p>
        </template>
        <template v-else-if="store.loaded && store.status && store.status.driver !== 'ready'">
          <span class="offline-icon pulse"><Icon name="home" :size="28" /></span>
          <h1 class="display">{{ store.restoring ? 'Restoring your house' : store.updating ? 'Updating the hub' : store.status.driver === 'down' ? 'The engine is starting' : 'Reconnecting' }}</h1>
          <p>{{ store.restoring || store.updating ? 'A few minutes. The lights and switches keep working; this screen comes back on its own.' : store.status.reason || 'The house will be back in a moment. Nothing needs doing.' }}</p>
        </template>
        <template v-else-if="store.error">
          <span class="offline-icon"><Icon name="home" :size="28" /></span>
          <h1 class="display">Can't reach the hub</h1>
          <p>Make sure the hub is powered on and this screen is on the same network. It will reconnect on its own.</p>
          <!-- No Restart here on purpose: there is nobody listening to ask. This is the floor of the
               ladder, and the physical answer is the only one left. docs/restart.md, piece 5. -->
          <p class="keeps">If this lasts a few minutes, unplug the hub for ten seconds and plug it back in.</p>
          <button class="button" @click="load()"><Icon name="refresh" :size="18" /> Try again</button>
        </template>
        <template v-else>
          <span class="offline-icon pulse"><Icon name="home" :size="28" /></span>
          <p class="empty">Finding the house…</p>
        </template>
      </div>
      <Transition v-else name="view" mode="out-in">
        <RoomView v-if="room" :key="room.id" :room="room" @back="open(null)" @open="open" />
        <RoomsView v-else-if="nav === 'top' && tab === 'rooms'" key="rooms" :rooms="rooms" :woke="woke" @open="open" />
        <CamerasView v-else-if="nav === 'top' && tab === 'cameras'" key="cameras" :rooms="rooms" :woke="woke" />
        <RailView v-else-if="layout === 'rail'" key="home-rail" :rooms="rooms" :now="shown" :top-nav="nav === 'top'" :woke="woke" @open="open" />
        <WallView v-else-if="layout === 'wall'" key="home-wall" :rooms="rooms" :now="shown" :top-nav="nav === 'top'" :woke="woke" @open="open" />
        <HomeView v-else key="home-stack" :rooms="rooms" :now="shown" :top-nav="nav === 'top'" @open="open" />
      </Transition>
    </main>

    <Household v-if="!setup && !shut && nav === 'top'" :room="room?.id ?? null" />

    <Viewer />
    <Opened v-if="store.opened" />
    <WeatherPane v-if="store.outside" :now="shown" />
    <AskPane v-if="asking" />
    <!-- :duration because what moves is inside: Vue times a transition from the
         element it is put on, and this one's root never moves, so on the way out
         it was pulling the panel off the screen before it had slid anywhere.
         These two numbers are the panel's own slide and the veil's fade. -->
    <Transition name="house" :duration="{ enter: 420, leave: 320 }"><HousePanel v-if="panel" /></Transition>
    <Transition name="sheet"><WhySheet v-if="store.sheet === 'why'" /></Transition>
    <!-- A bridge being set up opens itself: somebody has just plugged a thing in, in this room, and
         is standing here. It is not a place in the house to navigate to. -->
    <Transition name="sheet"><BridgeSheet v-if="store.bridge && store.bridge.state !== 'none'" /></Transition>
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
