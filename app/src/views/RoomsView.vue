<script setup lang="ts">
/*
 * The Rooms tab: the whole house at once, ranked. design/rooms/Main.dc.html.
 *
 * It used to be `<RoomGrid>` -- every room the same box, in the order the brain
 * returned them, in the top third of the screen. The grid is still what the
 * three home layouts use, where it is one band among several; here it is the
 * whole stage, and the whole stage is what it should fill.
 *
 * The arrangement is the room screen's: three heights, columns filling down and
 * then running off to the RIGHT. What goes over the right edge is therefore
 * always the quiet end of the house -- ranking decides what is hidden, rather
 * than whatever happened to land below a fold.
 */
import { computed, ref, watch } from 'vue'
import type { Room } from '../api'
import { houseLine } from '../store'
import { arrangeRooms, type Cell } from '../rooms'
import { useArrive } from '../arrive'
import RoomCard from '../RoomCard.vue'

/* woke: how many times the panel has come back from rest, so the house arrives
   again rather than only when the tab is first opened -- the same prop the two
   wall homes take, for the same reason. */
const props = defineProps<{ rooms: Room[]; woke?: number }>()
defineEmits<{ open: [id: string] }>()

/* The house comes in from the right, one card after another from the left, and
   the entrance doubles as the row's own instruction: a card travels the way a
   sweep would take it, so the side they arrive from is the side there is more
   on. Home's row has always said that; this arrangement sweeps the same way, so
   it says it the same way. */
const flow = useArrive(() => !props.rooms.length, () => props.woke)

/*
 * Decided when you open the tab, and then HELD -- the room screen's rule, for
 * the room screen's reason. Ranked live, turning the kitchen off from its own
 * card would re-rank the house, resize two cards and reflow every column, so
 * the cards would move under the finger that had just tapped one and a second
 * tap would land on a different room. The cards stay live; only their size and
 * their order are frozen, and they are recomputed when a room is added or
 * taken away.
 */
const plan = ref<Cell[]>([])
const byId = computed(() => new Map(props.rooms.map(r => [r.id, r])))
watch(
  () => props.rooms.map(r => r.id).join(),
  () => (plan.value = arrangeRooms(props.rooms)),
  { immediate: true },
)
</script>

<template>
  <section class="rooms">
    <!-- The tab behind this is already lit and says "Rooms", so a 56px heading
         saying it again cost 57px of stage to tell nobody anything. The house
         line is the same row spent on something only the house knows. -->
    <header class="stage-head rooms-head">
      <h1 class="display">{{ houseLine() }}</h1>
    </header>
    <!-- --flow-i is the card's place in the reading order: the entrance leans
         on it for the stagger, so the lead room is home first and the quiet end
         of the house last -->
    <div class="rooms-bento" :class="flow">
      <template v-for="(c, i) in plan" :key="c.id">
        <RoomCard v-if="byId.get(c.id)" :room="byId.get(c.id)!" :size="c.size" :style="{ '--flow-i': i }" @open="$emit('open', $event)" />
      </template>
    </div>
  </section>
</template>
