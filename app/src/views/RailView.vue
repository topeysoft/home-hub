<script setup lang="ts">
/*
 * Home as a rail: what is on now in one row you sweep through, instead of a
 * column you scroll. Made for a wall, where the whole screen is in view at once
 * and reaching the bottom of a page means walking to it.
 *
 * It shows the same devices as the Stack layout and uses the same tile
 * components, so dimming a light or pausing a film behaves identically — only
 * the arrangement differs. <Attention /> comes first and unchanged: see
 * layout.ts for why that is not a per-layout decision.
 *
 * The row is composed, not just listed. As drawn: what is playing first and
 * tall; then the two glance cards -- a camera and the thermostat -- stacked in
 * one column; then the lit things; then the evening's two scenes as a card of
 * their own; then whatever is left. A row of equal boxes is a spreadsheet, and
 * the difference between that and a room is the one small column.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, cap, houseLine, scenesFor, weatherParts, whatsOn } from '../store'
import { wxOf } from '../sky'
import { upcomingLine } from '../upcoming'
import type { Device, Room } from '../api'
import Icon from '../Icon.vue'
import Attention from '../Attention.vue'
import RoomGrid from '../RoomGrid.vue'
import SceneBar from '../SceneBar.vue'
import CameraTile from '../tiles/CameraTile.vue'
import ClimateTile from '../tiles/ClimateTile.vue'
import LightTile from '../tiles/LightTile.vue'
import MediaTile from '../tiles/MediaTile.vue'
import PlainTile from '../tiles/PlainTile.vue'

/* topNav: the tabs are across the top, so the rooms have a tab of their own and
   the command box lives in the bar along the bottom -- neither is repeated here.
   woke: counts the times the panel has come back from rest, so the rail can
   arrive again rather than only on the first load. */
const props = defineProps<{ rooms: Room[]; now: Date; topNav?: boolean; woke?: number }>()
defineEmits<{ open: [id: string] }>()

const hour = computed(() => props.now.getHours())
const greeting = computed(() => hour.value < 5 ? 'Good night' : hour.value < 12 ? 'Good morning' : hour.value < 17 ? 'Good afternoon' : hour.value < 21 ? 'Good evening' : 'Good night')
const line = computed(houseLine)
const next = computed(() => upcomingLine(props.now))
/* the scenes card is named for the part of the day it serves, like the greeting */
const when = computed(() => hour.value < 5 ? 'Tonight' : hour.value < 12 ? 'This morning' : hour.value < 17 ? 'This afternoon' : 'Tonight')

/* the weather, beside the greeting rather than in a card of its own: the sky
   behind the panel is already the forecast, so repeating it in a tile spends the
   best space on the screen saying what the screen is doing anyway. */
const wx = computed(() => wxOf(store.sky.condition))
const night = computed(() => store.sky.elevation < 3)
const temp = computed(() => weatherParts().temp)
const says = computed(() => weatherParts().label)
/* one illustration, assembled from the same numbers the sky is drawn from, so the
   two can never disagree — and a new condition needs no new artwork */
const cloudy = computed(() => wx.value.clouds)
const cloudScale = computed(() => (0.66 + cloudy.value * 0.34).toFixed(3))
const cloudShift = computed(() => (105 * (1 - Number(cloudScale.value))).toFixed(1) + ' ' + (100 * (1 - Number(cloudScale.value))).toFixed(1))
const drops = computed(() => !wx.value.rain ? '' : Array.from({ length: Math.round(2 + wx.value.rain * 3) }, (_, i) => `M${62 + i * 26} 118 l-7 22`).join(' '))
const flakes = computed(() => !wx.value.snow ? '' : Array.from({ length: Math.round(2 + wx.value.snow * 3) }, (_, i) => {
  const x = 66 + i * 26, y = 124 + (i % 2) * 12, r = 5
  return `M${x} ${y} m-${r} 0 a${r} ${r} 0 1 0 ${2 * r} 0 a${r} ${r} 0 1 0 -${2 * r} 0`
}).join(' '))

/* The rail's cards, in the order drawn. A device is a card; the scenes are one
   card among them ('scenes'), so the grid can place them all the same way. */
type Card = { key: string; kind: 'device' | 'scenes'; device?: Device }
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))
const climates = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'climate')))
const on = computed(() => whatsOn().filter(d => cap(d) !== 'camera' && cap(d) !== 'climate'))
const scenes = computed(() => scenesFor(null).length > 0)
const cards = computed<Card[]>(() => {
  const dev = (d: Device): Card => ({ key: d.id, kind: 'device', device: d })
  const playing = on.value.find(d => cap(d) === 'media' && d.state === 'playing') ?? on.value.find(d => cap(d) === 'media')
  const tall = on.value.filter(d => d !== playing).slice(0, 8)
  /* the glance cards, two to a column: the first column pairs a camera with the
     thermostat, as drawn, and the rest follow in their own columns at the end */
  const [cam0, ...cams] = cameras.value, [clim0, ...clims] = climates.value
  const small = [cam0, clim0, ...cams, ...clims].filter((d): d is Device => !!d)
  const out: Card[] = []
  if (playing) out.push(dev(playing))
  out.push(...small.slice(0, 2).map(dev))
  out.push(...tall.slice(0, 1).map(dev))
  if (scenes.value) out.push({ key: 'scenes', kind: 'scenes' })
  out.push(...tall.slice(1).map(dev))
  out.push(...small.slice(2).map(dev))
  return out
})
const empty = computed(() => !cards.value.length)
const tile = (d: Device) => cap(d) === 'light' ? LightTile : cap(d) === 'media' ? MediaTile : cap(d) === 'climate' ? ClimateTile : cap(d) === 'camera' ? CameraTile : PlainTile

const clock = ref(Date.now())
let t: number | undefined
onMounted(() => { t = window.setInterval(() => (clock.value = Date.now()), 20000) })
onUnmounted(() => clearInterval(t))

/* the rail's edge fade is CSS where the browser can drive it from scroll; the
   fallback mask only needs to know when an end has nothing beyond it */
const bento = ref<HTMLElement | null>(null)
const scrollDriven = typeof CSS !== 'undefined' && CSS.supports?.('animation-timeline: view()')
function edges() {
  const el = bento.value; if (!el || scrollDriven) return
  el.toggleAttribute('data-at-start', el.scrollLeft <= 1)
  el.toggleAttribute('data-at-end', el.scrollLeft + el.clientWidth >= el.scrollWidth - 1)
}
onMounted(() => { edges(); bento.value?.addEventListener('scroll', edges, { passive: true }); addEventListener('resize', edges) })
onUnmounted(() => { bento.value?.removeEventListener('scroll', edges); removeEventListener('resize', edges) })

/*
 * The rail arrives. On the first load, on waking from rest, and on coming back
 * from a room, the cards come in from off the right edge one after another,
 * left to right, and settle.
 *
 * It is two things in one move: a screen coming to life, and the row saying
 * which way it goes. They travel the way a swipe would take them, so the
 * direction they arrive from is the direction there is more in -- a flow the
 * other way would look just as pretty and point at nothing.
 *
 * Done as a transition rather than an animation on purpose: each card already
 * carries the two scroll-driven animations that soften the row's edges, and a
 * third would have to be merged into the same animation-* lists. `translate` is
 * a property neither of them touches. Nothing is left on a card once it is
 * home, so a held card, a dimmer drag and the edge fade all behave as if this
 * had never happened.
 */
const flow = ref<'' | 'set' | 'go'>('')
const stillMoves = !matchMedia('(prefers-reduced-motion: reduce)').matches
let settle: number | undefined
function arrive() {
  if (!stillMoves || empty.value) return       // reduced motion: the row is simply there, and never left mid-slide
  flow.value = 'set'                           // every card a step to the right of where it belongs, no transition
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (flow.value !== 'set') return
    flow.value = 'go'
    clearTimeout(settle)
    settle = window.setTimeout(() => (flow.value = ''), 1300)   // past the last card's 56ms x 9 wait plus its 560ms, so none is cut off mid-slide
  }))
}
onMounted(arrive)
watch(() => props.woke, arrive)
onUnmounted(() => clearTimeout(settle))
</script>

<template>
  <section class="home rail-home" :class="{ 'top-nav': topNav }">
    <header class="stage-head rail-head">
      <div class="rail-greet">
        <h1 class="display">{{ greeting }}</h1>
        <p class="lede">{{ line }}</p>
        <p class="home-next" v-if="next"><Icon name="sparkle" :size="14" />{{ next }}</p>
      </div>
      <div class="rail-wx" v-if="temp || says">
        <svg class="rail-cloud" viewBox="0 0 210 150" aria-hidden="true">
          <defs>
            <radialGradient id="railcloud" cx="34%" cy="28%" r="78%">
              <stop offset="0" stop-color="#ffffff" stop-opacity=".97" />
              <stop offset="62%" stop-color="#d8dce6" stop-opacity=".93" />
              <stop offset="100%" stop-color="#9aa3b4" stop-opacity=".85" />
            </radialGradient>
          </defs>
          <circle cx="150" cy="44" r="27" :fill="night ? '#dfe4ee' : '#f6dca8'" :opacity="0.25 + (1 - Math.min(1, cloudy / 0.55)) * 0.75" />
          <g :transform="`translate(${cloudShift}) scale(${cloudScale})`" :opacity="cloudy < 0.1 ? 0.34 : 1" fill="url(#railcloud)">
            <ellipse cx="72" cy="86" rx="56" ry="40" /><ellipse cx="118" cy="70" rx="48" ry="44" />
            <ellipse cx="150" cy="94" rx="42" ry="30" /><rect x="60" y="92" width="104" height="34" rx="17" />
          </g>
          <path v-if="wx.lightning" d="M112 96 L86 132 h20 l-6 26 28-38 h-20 z" fill="#f3d18a" />
          <path v-if="drops" :d="drops" stroke="#9fc3e8" stroke-width="4" stroke-linecap="round" fill="none" :opacity="0.45 + wx.rain * 0.55" />
          <path v-if="flakes" :d="flakes" fill="#e6ecf5" :opacity="0.5 + wx.snow * 0.5" />
          <path v-if="wx.fog" d="M22 112h58 M96 112h92 M40 132h64 M118 132h54" stroke="#aab2bd" stroke-width="6" stroke-linecap="round" fill="none" :opacity="wx.fog * 0.72" />
        </svg>
        <div class="rail-wx-text">
          <div class="rail-temp display" v-if="temp">{{ temp }}</div>
          <div class="rail-says">{{ says }}</div>
        </div>
      </div>
    </header>

    <Attention :say="!topNav" />

    <!-- the rail sits in the middle of whatever height is left, as drawn; the
         rooms, when they are here at all, wait underneath -->
    <div class="rail-stage">
      <!-- --flow-i is the card's place in the row: the entrance leans on it for the stagger -->
      <div class="bento" ref="bento" v-if="!empty" :class="flow" role="group" aria-label="On right now">
        <template v-for="(c, i) in cards" :key="c.key">
          <component v-if="c.kind === 'device'" :is="tile(c.device!)" class="bento-card" :style="{ '--flow-i': i }" :device="c.device!" v-hold="() => (store.opened = c.device!)" />
          <div v-else class="bento-card tile scene-card" :style="{ '--flow-i': i }">
            <span class="scene-card-when">{{ when }}</span>
            <SceneBar :room="null" />
          </div>
        </template>
      </div>
      <p class="empty rail-quiet" v-else>Nothing is on.{{ topNav ? '' : ' The rooms are below.' }}</p>
    </div>

    <div class="block" v-if="!topNav">
      <h2 class="label">Rooms</h2>
      <RoomGrid :rooms="rooms" @open="$emit('open', $event)" />
    </div>
  </section>
</template>
