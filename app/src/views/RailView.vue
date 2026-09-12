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
 * What this file is, then, is where the row SITS: under a greeting, with the
 * weather in the corner beside it. The row itself is BentoRow, which Wall uses
 * too and which knows nothing about either arrangement.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { houseLine, weatherParts } from '../store'
import { upcomingLine } from '../upcoming'
import type { Room } from '../api'
import Icon from '../Icon.vue'
import Attention from '../Attention.vue'
import RoomGrid from '../RoomGrid.vue'
import WeatherArt from '../WeatherArt.vue'
import BentoRow from './BentoRow.vue'

/* topNav: the tabs are across the top, so the rooms have a tab of their own and
   the command box lives in the bar along the bottom -- neither is repeated here.
   woke: counts the times the panel has come back from rest; the row takes it. */
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
const temp = computed(() => weatherParts().temp)
const says = computed(() => weatherParts().label)

const clock = ref(Date.now())
let t: number | undefined
onMounted(() => { t = window.setInterval(() => (clock.value = Date.now()), 20000) })
onUnmounted(() => clearInterval(t))

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
        <WeatherArt class="rail-cloud" />
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
      <BentoRow :rooms="rooms" :when="when" :woke="woke">
        <template #quiet>
          <p class="empty rail-quiet">Nothing is on.{{ topNav ? '' : ' The rooms are below.' }}</p>
        </template>
      </BentoRow>
    </div>

    <div class="block" v-if="!topNav">
      <h2 class="label">Rooms</h2>
      <RoomGrid :rooms="rooms" @open="$emit('open', $event)" />
    </div>
  </section>
</template>
