<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, activity, cap, openWhy, isDead } from '../store'
import { setByLine } from '../why'
import { readingLabel, readingName, isReading, readingOn } from '../readings'
import type { Room } from '../api'
import Icon from '../Icon.vue'
import SceneBar from '../SceneBar.vue'
import LightTile from '../tiles/LightTile.vue'
import MediaTile from '../tiles/MediaTile.vue'
import CameraTile from '../tiles/CameraTile.vue'
import PlainTile from '../tiles/PlainTile.vue'
import ClimateTile from '../tiles/ClimateTile.vue'
import SortView from '../SortView.vue'

const props = defineProps<{ room: Room }>()
defineEmits<{ back: []; open: [id: string] }>()
const editing = ref(false)
/* an empty room is not a dead end: things waiting under New devices can be placed here, or something new added */
const waiting = computed(() => store.rooms.find(r => r.id === 'unassigned')?.devices.length ?? 0)

const order = ['media', 'light', 'cover', 'lock', 'fan', 'switch', 'vacuum', 'climate', 'camera', 'motion', 'contact', 'sensor']
const sorted = computed(() => [...props.room.devices].sort((a, b) => order.indexOf(cap(a)) - order.indexOf(cap(b))))
const readings = computed(() => sorted.value.filter(isReading))      // sensors say something; they are read, not tapped
const devices = computed(() => sorted.value.filter(d => !isReading(d)))
const tile = (c: string) => c === 'light' ? LightTile : c === 'media' ? MediaTile : c === 'camera' ? CameraTile : c === 'climate' ? ClimateTile : PlainTile

/* Who set this room, and how long a hand keeps routines away. Ticks so "1 h 20 min left" stays true. */
const now = ref(Date.now())
const setBy = computed(() => setByLine(props.room, now.value))
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 30000) })
onUnmounted(() => clearInterval(tick))
</script>

<template>
  <SortView v-if="room.id === 'unassigned'" :room="room" @back="$emit('back')" />
  <SortView v-else-if="editing" :room="room" editing @back="editing = false" />
  <section class="room" v-else>
    <header class="stage-head room-head">
      <button class="back" @click="$emit('back')" aria-label="Back to home"><Icon name="back" :size="22" /></button>
      <div>
        <h1 class="display">{{ room.name }}</h1>
        <p class="lede">{{ activity(room) }}</p>
      </div>
      <button class="back room-edit" @click="editing = true" aria-label="Edit this room" title="Rename or move things"><Icon name="edit" :size="20" /></button>
    </header>

    <SceneBar :room="room" />
    <button class="why-line" v-if="setBy" @click="openWhy(room.id)" title="Why is this room like this?">
      <Icon :name="setBy.icon" :size="15" /><span>{{ setBy.text }}</span><span class="why-ask">Why?</span>
    </button>

    <div class="readings" v-if="readings.length" aria-label="Readings">
      <span v-for="d in readings" :key="d.id" class="reading" :class="{ on: readingOn(d), dead: isDead(d) }">
        <Icon :name="cap(d)" :size="15" /><span class="reading-name" v-if="readingName(d, room)">{{ readingName(d, room) }}</span><span class="reading-value">{{ readingLabel(d) }}</span>
      </span>
    </div>
    <div class="tiles" v-if="devices.length">
      <component v-for="d in devices" :key="d.id" :is="tile(cap(d))" :device="d" />
    </div>
    <div v-else-if="!readings.length" class="empty-room">
      <p class="empty">Nothing in this room yet.</p>
      <p class="empty-sub" v-if="waiting">{{ waiting === 1 ? 'One new device is' : `${waiting} new devices are` }} waiting to be placed. One of them may belong here.</p>
      <p class="empty-sub" v-else>Add something and say it lives in the {{ room.name }}; it shows up here on its own.</p>
      <div class="empty-actions">
        <button class="button" v-if="waiting" @click="$emit('open', 'unassigned')"><Icon name="sparkle" :size="16" /> Place new devices</button>
        <button class="button" :class="{ ghost: waiting }" @click="store.sheet = 'add'"><Icon name="plus" :size="16" /> Add a device</button>
      </div>
    </div>
  </section>
</template>
