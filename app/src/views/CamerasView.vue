<script setup lang="ts">
/*
 * The Cameras tab of the Top navigation: every camera in the house, each a tap
 * to watch and a hold to open.
 *
 * The frame is the Rooms tab's, for the Rooms tab's reason: the stage does not
 * scroll, the head stays where it is, and what does not fit runs off to the
 * RIGHT. This used to be a grid that wrapped DOWNWARDS inside a scrolling
 * stage, and because a camera tile is `.tile.wide` -- two columns of the grid
 * the room screen used to use -- only one of them fitted on a row. Three
 * cameras made a 1483px column inside a 618px stage: the heading scrolled away
 * and the last camera was cut off behind the command box.
 *
 * Rows are counted here rather than in CSS because only the browser knows how
 * many frames fit across: one row while they all fit, two once they do not, and
 * the rest of the house off to the right. A row is then capped at 4:3 of the
 * frame's own width. Without the cap a house with three cameras would stretch
 * three frames down the whole stage and `object-fit: cover` would crop each
 * 16:9 view to portrait -- throwing away two thirds of the scene the camera was
 * put up to watch, which is a strange way to fill a screen.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Room } from '../api'
import { cap, store } from '../store'
import { useArrive } from '../arrive'
import CameraTile from '../tiles/CameraTile.vue'

const props = defineProps<{ rooms: Room[]; woke?: number }>()
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))
/* The lift, not the sweep: the frames come up from below as one block. That was
   chosen when this grid wrapped downwards; the grid runs right now, so the case
   for the sweep Rooms uses is open, and e2e/arrive.spec.ts pins the lift until
   somebody decides. Either way it is the same entrance, not a second one. */
const flow = useArrive(() => !cameras.value.length, () => props.woke)

const GAP_X = 20, GAP_Y = 16     // the gaps in .cameras-all; measuring beats guessing but not by enough to read the sheet
const WIDEST = 4 / 3             // the squarest a 16:9 frame may be squeezed before it is left short instead

const grid = ref<HTMLElement>()
const rows = ref(1)
const rowHeight = ref(0)
function measure() {
  const el = grid.value
  const first = el?.firstElementChild as HTMLElement | undefined
  if (!el || !first || !cameras.value.length) return
  const cell = first.getBoundingClientRect().width || 340       // the column width CSS chose for this screen
  const across = Math.max(1, Math.floor((el.clientWidth + GAP_X) / (cell + GAP_X)))
  const r = cameras.value.length <= across ? 1 : 2
  // Exact heights rather than fractions: a row that is capped must not be able to push its neighbour
  // past the bottom of a stage that no longer scrolls.
  const share = Math.floor((el.clientHeight - (r - 1) * GAP_Y) / r)
  rows.value = r
  rowHeight.value = Math.max(0, Math.min(share, Math.round(cell / WIDEST)))
}

let watching: ResizeObserver | undefined
onMounted(() => { measure(); watching = new ResizeObserver(measure); if (grid.value) watching.observe(grid.value) })
onUnmounted(() => watching?.disconnect())
watch(() => cameras.value.length, () => nextTick(measure))
</script>

<template>
  <section class="cameras">
    <header class="stage-head"><h1 class="display">Cameras</h1></header>
    <div
      class="cameras-all" ref="grid" :class="flow" v-if="cameras.length"
      :style="{ '--cam-rows': rows, '--cam-row': rowHeight ? `${rowHeight}px` : '1fr' }"
    >
      <CameraTile v-for="(c, i) in cameras" :key="c.id" :device="c" :style="{ '--flow-i': i }" v-hold="() => (store.opened = c)" />
    </div>
    <p class="empty" v-else>No cameras yet. Add one and it shows up here on its own.</p>
  </section>
</template>
