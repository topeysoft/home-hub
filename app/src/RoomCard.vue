<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * One room on the Rooms tab, at one of four sizes. design/rooms/Main.dc.html,
 * and design/rooms/QuietIndex.dc.html for the smallest.
 *
 * Size is not decoration: it is how much the room is allowed to SAY, and the
 * card grows a row at a time rather than becoming a different card. A row is
 * the name and the line, laid along. A third is the same two laid down. A half
 * adds the drawing of the room lit and the dimmer for the lamp doing the
 * lighting. The full adds the row for what is playing. Every size keeps the
 * name and the line in the same place and in the same order, so a room that
 * changes size between visits is still the same object.
 */
import { computed, onMounted, ref } from 'vue'
import { imageUrl, type Room } from './api'
import { activityParts, cap, isDead, perform, restingLine, runScene, scenesFor, shortName, store } from './store'
import { leadLight, playingIn, temperature, type Size } from './rooms'
import { kindFor } from './art'
import { useStill } from './still'
import Icon from './Icon.vue'
import DeviceArt from './DeviceArt.vue'

const SLOW = 30000     // a room card is a glance across the house, not the camera screen
const props = defineProps<{ room: Room; size: Size }>()
defineEmits<{ open: [id: string] }>()

const empty = computed(() => !props.room.devices.length)
const waiting = computed(() => props.room.id === 'unassigned')
const media = computed(() => playingIn(props.room))
const lamp = computed(() => leadLight(props.room))
const temp = computed(() => temperature(props.room))
const line = computed(() => props.size === 'full' && media.value
  ? activityParts(props.room, false).join(' · ') || restingLine(props.room)   // the media has a row of its own below
  : restingLine(props.room))
/* the lamps worth naming on the card that has room to name them: the one doing
   the lighting, and at most one more. A third light is a number, not a row. */
const lamps = computed(() =>
  props.room.devices.filter(d => cap(d) === 'light' && d.state === 'on')
    .sort((a, b) => Number(b.attrs.brightness ?? 255) - Number(a.attrs.brightness ?? 255))
    .slice(0, 2))
const pct = (d: { attrs: Record<string, any> }) => Math.round((Number(d.attrs.brightness ?? 255) / 255) * 100)
const camera = computed(() => props.room.devices.find(d => cap(d) === 'camera'))
const filming = computed(() => camera.value?.state === 'recording')
/* What the room's card is FOR at a glance, when there is no picture to show.
   The same ranking the room screen sorts its tiles by, stopped at the first
   thing that is doing something -- a bedroom is its fan while the fan is on and
   its lamp the rest of the time. */
const ORDER = ['media', 'light', 'lock', 'camera', 'fan', 'cover', 'switch', 'vacuum', 'climate']
const lead = computed(() => {
  const ranked = props.room.devices.filter(d => ORDER.includes(cap(d)))
    .sort((a, b) => ORDER.indexOf(cap(a)) - ORDER.indexOf(cap(b)))
  return ranked.find(d => d.state !== 'off' && !isDead(d)) ?? ranked[0]
})
const mark = computed(() => waiting.value ? 'sparkle' : lead.value ? cap(lead.value) : '')
/* the drawing a half is big enough for: rung two, the one the tiles already use */
const draw = computed(() => lead.value ? kindFor(cap(lead.value), lead.value.name) : null)

/* the one thing a room card can do without going into the room. Only offered
   when the room actually qualifies for All off -- a card that promises to turn
   off a room with nothing in it to turn off is worse than no button. */
const allOff = computed(() => scenesFor(props.room).find(s => s.id === 'empty'))
const lit = computed(() => props.room.devices.some(d => d.state === 'on' || d.state === 'playing'))
function turnOff() { const s = allOff.value; if (s) runScene(props.room, s) }
const toggleMedia = () => { const d = media.value; if (d) perform(d, 'pause', undefined, { state: 'paused' }) }

/* A camera room brings its own picture and it beats anything we can draw. This
   used to be one frame taken when the tab opens, which on a camera that only
   updates on motion could leave last night on the wall all day. It is watched
   now instead -- slowly, and shared with the room's own tiles, so a wall of
   cards is still one fetch per camera and not one per card. The viewer is one
   tap away and it is live. */
const wantsStill = computed(() =>
  !!camera.value && camera.value.state !== 'unavailable' &&
  (filming.value || props.room.devices.every(d => cap(d) === 'camera')))
const watched = useStill(() => wantsStill.value ? camera.value?.id : undefined, SLOW)
const still = computed(() => watched.value.url)
const art = ref('')
onMounted(() => { if (media.value?.attrs.entity_picture) art.value = imageUrl(media.value.id) })
</script>

<template>
  <!--
    A room with nothing on has one sentence to its name, and a row is the size of
    one sentence. It is the same object as the card and not a different one: the
    same way in underneath, the same name and the same line in the same order,
    laid along instead of down. What it drops is the furniture that sentence was
    never using. See rooms.ts for when a room gets one.
  -->
  <div v-if="size === 'row'" class="room-cell" :class="{ empty, waiting }" data-size="row">
    <button class="room-cell-open" @click="$emit('open', room.id)" :aria-label="`Open ${room.name}`"></button>
    <span class="room-cell-glow" v-if="waiting" aria-hidden="true"></span>
    <span class="room-cell-badge" aria-hidden="true"><Icon v-if="mark" :name="mark" :size="18" /></span>
    <div class="room-cell-foot">
      <div class="room-cell-name">{{ room.name }}</div>
      <div class="room-cell-line">{{ line }}</div>
    </div>
    <span class="room-cell-chip" v-if="temp"><Icon name="sensor" :size="14" />{{ temp }}</span>
    <!-- the tray of things waiting to be placed is the one row with something to
         ask, and it keeps the button it asks with -->
    <button class="room-cell-pill ghost" v-if="waiting" @click.stop="store.sheet = 'add'">
      <Icon name="plus" :size="16" /> Add
    </button>
  </div>

  <div v-else class="room-cell" :class="[size, { lit, empty, waiting, filming, shot: !!still || !!art }]" :data-size="size">
    <!-- the whole card is the way in; the controls sit above it -->
    <button class="room-cell-open" @click="$emit('open', room.id)" :aria-label="`Open ${room.name}`"></button>

    <img v-if="still" class="room-cell-still" :src="still" alt="" />
    <img v-else-if="art" class="room-cell-art" :src="art" alt="" @error="art = ''" />
    <!-- the lamp bleeding off the corner: `.room-card.active` already draws it,
         and it is what says "on" without painting the room a different color -->
    <span class="room-cell-glow" v-if="lit || waiting" aria-hidden="true"></span>
    <span class="room-cell-veil" v-if="still || art" aria-hidden="true"></span>

    <!-- a half has the height to show the room lit rather than describe it -->
    <DeviceArt v-if="size === 'half' && !still && !art && draw" class="room-cell-draw"
      :kind="draw" :state="{ on: lit, brightness: lamp ? pct(lamp) / 100 : 1, playing: !!media, live: filming }" fit="slot" />

    <div class="room-cell-top">
      <span class="room-cell-cap" v-if="size === 'full' && lit"><i class="room-cell-dot"></i>On now</span>
      <span class="room-cell-chip live" v-else-if="filming"><i class="room-cell-dot rec"></i>Recording</span>
      <Icon v-else-if="mark" class="room-cell-mark" :name="mark" :size="20" />
      <span class="room-cell-chip" v-if="temp && size !== 'third'"><Icon name="sensor" :size="14" />{{ temp }}</span>
      <!-- the same act as the pill below, at the size that has no room for words -->
      <button class="room-cell-knob" v-if="size === 'half' && allOff && lit" @click.stop="turnOff"
        :aria-label="`Turn off the ${room.name}`" :title="`Turn off the ${room.name}`"><Icon name="power" :size="17" /></button>
    </div>

    <div class="room-cell-foot">
      <span class="room-cell-temp" v-if="temp && size === 'third'"><Icon name="sensor" :size="14" />{{ temp }}</span>
      <div class="room-cell-name">{{ room.name }}</div>
      <div class="room-cell-line">{{ line }}</div>

      <template v-if="size === 'full'">
        <!-- what is playing, given the row the line above it no longer spends -->
        <div class="room-cell-now" v-if="media">
          <span class="room-cell-thumb" :class="{ has: !!art }"><img v-if="art" :src="art" alt="" /></span>
          <span class="room-cell-now-text">
            <span class="room-cell-now-title">{{ media.attrs.media_title || shortName(media, room) }}</span>
            <span class="room-cell-now-sub" v-if="media.attrs.media_artist || media.attrs.app_name">{{ [media.attrs.media_artist, media.attrs.app_name].filter(Boolean).join(' · ') }}</span>
          </span>
          <button class="room-cell-play" @click.stop="toggleMedia" :aria-label="`Pause ${media.attrs.media_title || shortName(media, room)}`"><Icon name="pause" :size="17" /></button>
        </div>
        <div class="room-cell-lamp" v-for="d in lamps" :key="d.id">
          <Icon name="light" :size="16" />
          <span class="room-cell-lamp-name">{{ shortName(d, room) }}</span>
          <span class="room-cell-lamp-pct">{{ pct(d) }}%</span>
          <span class="room-cell-bar"><i :style="{ width: pct(d) + '%' }"></i></span>
        </div>
      </template>

      <!-- a half says what the lamp is doing with the room's own bar -->
      <span class="room-cell-bar" v-else-if="size === 'half' && lamp"><i :style="{ width: pct(lamp) + '%' }"></i></span>

      <button class="room-cell-pill" v-if="size === 'full' && allOff && lit" @click.stop="turnOff">
        <Icon name="power" :size="17" /> Turn the room off
      </button>
      <button class="room-cell-pill ghost" v-else-if="waiting" @click.stop="store.sheet = 'add'">
        <Icon name="plus" :size="16" /> Add something
      </button>
    </div>
  </div>
</template>
