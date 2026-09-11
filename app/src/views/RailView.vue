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
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, activity, cap, houseLine, roomActive, weatherParts, whatsOn } from '../store'
import { wxOf } from '../sky'
import { upcomingLine } from '../upcoming'
import type { Device, Room } from '../api'
import Icon from '../Icon.vue'
import Attention from '../Attention.vue'
import SceneBar from '../SceneBar.vue'
import CameraTile from '../tiles/CameraTile.vue'
import ClimateTile from '../tiles/ClimateTile.vue'
import LightTile from '../tiles/LightTile.vue'
import MediaTile from '../tiles/MediaTile.vue'
import PlainTile from '../tiles/PlainTile.vue'

const props = defineProps<{ rooms: Room[]; now: Date }>()
defineEmits<{ open: [id: string] }>()

const hour = computed(() => props.now.getHours())
const greeting = computed(() => hour.value < 5 ? 'Good night' : hour.value < 12 ? 'Good morning' : hour.value < 17 ? 'Good afternoon' : hour.value < 21 ? 'Good evening' : 'Good night')
const line = computed(houseLine)
const next = computed(() => upcomingLine(props.now))

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

/* the rail: what is on now, the cameras, and whatever is keeping the house warm.
   Room by room underneath, for everything that is not asking to be looked at. */
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))
const climates = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'climate')))
const on = computed(() => whatsOn().filter(d => cap(d) !== 'camera' && cap(d) !== 'climate'))
const carded = computed<Device[]>(() => [...on.value, ...climates.value].slice(0, 10))
const empty = computed(() => !cameras.value.length && !carded.value.length)

const clock = ref(Date.now())
let t: number | undefined
onMounted(() => { t = window.setInterval(() => (clock.value = Date.now()), 20000) })
onUnmounted(() => clearInterval(t))
</script>

<template>
  <section class="home rail-home">
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

    <Attention />

    <SceneBar :room="null" />

    <div class="bento" v-if="!empty" role="group" aria-label="On right now">
      <component
        v-for="d in carded" :key="d.id" class="bento-card"
        :is="cap(d) === 'light' ? LightTile : cap(d) === 'media' ? MediaTile : cap(d) === 'climate' ? ClimateTile : PlainTile"
        :device="d" />
      <CameraTile v-for="c in cameras" :key="c.id" :device="c" class="bento-card" />
    </div>
    <p class="empty rail-quiet" v-else>Nothing is on. The rooms are below.</p>

    <div class="block">
      <h2 class="label">Rooms</h2>
      <div class="room-grid">
        <button v-for="r in rooms" :key="r.id" class="room-card" :class="{ active: roomActive(r), empty: !r.devices.length, attention: r.id === 'unassigned' }" @click="$emit('open', r.id)">
          <div class="room-card-name">{{ r.name }}</div>
          <div class="room-card-activity">{{ activity(r) }}</div>
        </button>
      </div>
    </div>
  </section>
</template>
