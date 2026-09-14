<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, activity, cap, openWhy, isDead, scenesFor } from '../store'
import { setByLine } from '../why'
import { readingLabel, readingName, isReading, readingOn } from '../readings'
import type { Device, Room } from '../api'
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

/*
 * How much room a tile gets, and it is three heights and nothing else.
 *
 * A room does not scroll DOWN -- it fills in columns and runs off to the RIGHT
 * when there is more of it than fits. That is what keeps the way back on the
 * screen: not a sticky rule somebody can break later, but the fact that the
 * only axis that moves is one the head does not sit on. The cost of it is this
 * table: tile height is set by the screen rather than by the content, so every
 * tile has to be a full column, a half or a third, for ever. See design/room.
 *
 * Size is how much the tile has to SAY, which is the ranking made visible. A
 * media tile that is playing carries artwork, a title and transport. The lamp
 * actually lighting the room carries a drawing and a dimmer. A thing that is
 * off has one thing to say and that is its name.
 *
 * The numbers are row tracks, not pixels: a column is THREE slots whatever the
 * screen is, so the same three sizes hold at 800 and at 1080. Three and not six
 * because a column has to come out flush -- with six, a half beside a third
 * filled five sixths of one and left the room ragged along the bottom. Three
 * slots can only be filled exactly: one card, or a big and a small, or three
 * small.
 */
const SIZES = { full: 3, half: 2, third: 1 } as const
type Size = keyof typeof SIZES

/* only ONE lamp leads. A room with four lights on is not a room with four
   headlines in it -- the one doing the most of the lighting is the one worth
   the drawing, and the rest are a name and a number. */
const brightest = computed(() => {
  const lit = props.room.devices.filter(d => cap(d) === 'light' && d.state === 'on')
  return [...lit].sort((a, b) => Number(b.attrs.brightness ?? 0) - Number(a.attrs.brightness ?? 0))[0]?.id ?? null
})

function sizeOf(d: Device): Size {
  if (isDead(d)) return 'third'                                     // nothing to say but that it stopped answering
  const c = cap(d)
  if (c === 'media' && d.state === 'playing') return 'full'
  if (c === 'media') return 'third'                                 // paused, it keeps its artwork and one button, and that fits in a third -- which is how both boards draw it
  if (d.id === brightest.value) return 'half'
  if (c === 'camera') return 'half'                                 // it brings a picture, and a picture needs room
  return 'third'                                                    // a thermostat with it: the number and what it is doing fit, and the dial is in the pane
}

/* Bigger first, and within a size the things that are doing something before
   the things that are not. Equal sizes ending up adjacent is not a nicety: it
   is what lets a column pack full instead of leaving a hole halfway down. */
const doing = (d: Device) => !isDead(d) && d.state !== 'off' && d.state !== 'unavailable'
type Cell = { key: string; size: Size }

function arrange(): Cell[] {
  const ds: Cell[] = [...devices.value]
    .sort((a, b) =>
      SIZES[sizeOf(b)] - SIZES[sizeOf(a)] ||
      Number(doing(b)) - Number(doing(a)) ||
      order.indexOf(cap(a)) - order.indexOf(cap(b)))
    .map(d => ({ key: d.id, size: sizeOf(d) }))
  if (!scenesFor(props.room).length) return ds
  /* The scenes are a CARD among the devices rather than a bar above them. A bar
     costs 62px off the top of every room in the house before anything in the
     room is shown, and nothing about four scenes is more urgent than the lamp
     that is actually on. They go SECOND -- whatever leads the room leads it,
     and the way to change the whole room is the next thing you reach. Putting
     them first made a kitchen with nothing playing open on its own scene list,
     which reads as a menu rather than as a room.

     A FULL column, because the line under each scene is what makes the card
     readable from the other side of a room -- "All off" and "Lights off, media
     paused" are not the same promise -- and four scenes with their hints do not
     fit in a half however they are set. The cost is one column, and a room
     running a column wider is what this arrangement is for: what goes over the
     right edge is what is OFF. */
  return [...ds.slice(0, 1), { key: 'scenes', size: 'full' }, ...ds.slice(1)]
}

/*
 * The arrangement is decided when you walk into the room, and then HELD.
 *
 * This is not an optimisation, it is the whole difference between a panel you
 * can use and one you cannot. Ranked live, turning the main lamp off promoted
 * the next-brightest one, resized both, and reflowed every column -- so on a
 * wall panel the tiles moved under the finger that had just tapped, and a
 * second tap in the same place landed on whatever had slid into the gap. A test
 * caught it by tapping a light twice and getting two different devices.
 *
 * So the plan is recomputed when the room CHANGES or when something is added to
 * it or taken away, and never merely because something in it was switched on.
 * A room is arranged for the state you found it in; it rearranges next time you
 * walk up to it. The tiles themselves stay live -- only their size and their
 * order are frozen, and the device is looked up fresh on every render.
 */
const plan = ref<Cell[]>([])
const byId = computed(() => new Map(props.room.devices.map(d => [d.id, d])))
watch(
  () => `${props.room.id}|${devices.value.map(d => d.id).join()}`,
  () => (plan.value = arrange()),
  { immediate: true },
)
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
        <!-- Why the room is like this, and what it can tell you, on ONE line --
             and inside the head rather than under it, so it lines up with the
             room's name instead of with the edge of the screen. These were two
             stacked bands with a scene bar above them: three rows where one
             does, and between them they spent 400 of the stage's 618px before
             the first device. -->
        <div class="room-line" v-if="setBy || readings.length" aria-label="Readings">
          <button class="why-line" v-if="setBy" @click="openWhy(room.id)" title="Why is this room like this?">
            <Icon :name="setBy.icon" :size="15" /><span>{{ setBy.text }}</span><span class="why-ask">Why?</span>
          </button>
          <!-- A reading can be held open like anything else. It is the only way in for the three
               kinds that have no tile -- motion, a thermometer, a door contact -- and it costs the
               room nothing, because the strip is already here. -->
          <button v-for="d in readings" :key="d.id" class="reading" :class="{ on: readingOn(d), dead: isDead(d) }"
                  v-hold="() => (store.opened = d)" :title="`Hold to open ${d.name}`">
            <Icon :name="cap(d)" :size="15" /><span class="reading-name" v-if="readingName(d, room)">{{ readingName(d, room) }}</span><span class="reading-value">{{ readingLabel(d) }}</span>
          </button>
        </div>
      </div>
      <button class="back room-edit" @click="editing = true" aria-label="Edit this room" title="Rename or move things"><Icon name="edit" :size="20" /></button>
    </header>

    <div class="tiles" v-if="devices.length">
      <template v-for="c in plan" :key="c.key">
        <div v-if="c.key === 'scenes'" class="tile room-scenes" :data-size="c.size">
          <span class="room-scenes-head">In the {{ room.name.toLowerCase() }}</span>
          <SceneBar :room="room" stacked />
        </div>
        <component v-else-if="byId.get(c.key)" :is="tile(cap(byId.get(c.key)!))" :data-size="c.size" :device="byId.get(c.key)!" v-hold="() => (store.opened = byId.get(c.key)!)" />
      </template>
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
