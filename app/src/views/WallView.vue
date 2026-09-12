<script setup lang="ts">
/*
 * Home as a wall: the weather given the left third of the screen, and what is
 * on beside it.
 *
 * The difference from Rail is what is NOT here. There is no greeting, no house
 * line and no next-up line, because on a panel read from across a room the top
 * of the screen is the most valuable space there is and a sentence you have
 * already read costs it. The date moves into the top bar, which was carrying it
 * anyway, and everything that is left is either the sky or something you can
 * touch. That is the whole arrangement: it is drawn in
 * design/nightfall/Main.dc.html, a 1440x900 board where the row starts 180px
 * down instead of two thirds of the way.
 *
 * The weather is not a card. The sky's drawing goes straight onto the field and
 * one lozenge of glass hangs in front of it, which is what makes the left third
 * read as depth rather than as an empty tile -- a card there would be a box
 * saying what the whole screen behind it is already saying.
 *
 * Everything else is shared: the same row, the same tiles, the same drawing of
 * the sky. <Attention /> comes first and unchanged -- see layout.ts for why
 * that is not a per-layout decision, and it is the one thing here the board
 * does not show, because the board has nothing to attend to.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, weatherParts } from '../store'
import { nextSun } from '../upcoming'
import type { Room } from '../api'
import Attention from '../Attention.vue'
import RoomGrid from '../RoomGrid.vue'
import WeatherArt from '../WeatherArt.vue'
import BentoRow from './BentoRow.vue'

const props = defineProps<{ rooms: Room[]; now: Date; topNav?: boolean; woke?: number }>()
defineEmits<{ open: [id: string] }>()

const hour = computed(() => props.now.getHours())
/* the scenes card is named for the part of the day it serves */
const when = computed(() => hour.value < 5 ? 'Tonight' : hour.value < 12 ? 'This morning' : hour.value < 17 ? 'This afternoon' : 'Tonight')

const temp = computed(() => weatherParts().temp)
const says = computed(() => weatherParts().label)

/* Two quiet lines under the weather, and both have to be things the house
   actually knows. The board says "Feels like 81°", which nothing here measures:
   a hub reports a temperature, a condition, humidity and wind, and inventing an
   apparent temperature from those would be the panel making up weather. So the
   lines are the sun -- computed from the location the sky is already drawn from
   -- and whichever of humidity or wind the house has. */
const sun = computed(() => {
  const up = store.sky.elevation > -0.833
  const at = nextSun(props.now, !up)
  if (!at) return ''
  return `${up ? 'Sunset' : 'Sunrise'} ${at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
})
const also = computed(() => {
  const w = store.ambient.weather
  if (w?.humidity != null) return `Humidity ${Math.round(w.humidity)}%`
  if (w?.wind_speed != null) return `Wind ${Math.round(w.wind_speed)} ${w.wind_unit ?? ''}`.trim()
  return ''
})

const clock = ref(Date.now())
let t: number | undefined
onMounted(() => { t = window.setInterval(() => (clock.value = Date.now()), 20000) })
onUnmounted(() => clearInterval(t))
</script>

<template>
  <section class="home wall-home" :class="{ 'top-nav': topNav }">
    <Attention :say="!topNav" />

    <div class="wall-stage">
      <!-- the sky, and the one pane of glass hung in front of it -->
      <div class="wall-wx" v-if="temp || says">
        <WeatherArt class="wall-cloud" />
        <div class="wall-loz">
          <div class="wall-temp" v-if="temp">{{ temp }}</div>
          <div class="wall-says" v-if="says">{{ says }}</div>
          <div class="wall-sub" v-if="sun">{{ sun }}</div>
          <div class="wall-sub dim" v-if="also">{{ also }}</div>
        </div>
      </div>

      <BentoRow :rooms="rooms" :when="when" :woke="woke">
        <template #quiet>
          <p class="empty wall-quiet">Nothing is on.{{ topNav ? '' : ' The rooms are below.' }}</p>
        </template>
      </BentoRow>
    </div>

    <div class="block" v-if="!topNav">
      <h2 class="label">Rooms</h2>
      <RoomGrid :rooms="rooms" @open="$emit('open', $event)" />
    </div>
  </section>
</template>
