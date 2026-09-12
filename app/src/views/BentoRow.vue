<script setup lang="ts">
/*
 * The row of what is on, and everything it knows how to do: compose itself,
 * arrive, and tell CSS where its edges are.
 *
 * It lives apart from any one arrangement because two of them use it. Rail puts
 * it under a greeting with the weather in the corner; Wall gives the weather the
 * left third and lets the row have the rest of the screen. Neither of those is a
 * fact about the row, and a row that had to be told which one it was in would be
 * a row that could disagree with itself in two places.
 *
 * The row is composed, not just listed. As drawn: what is playing first and
 * tall; then the two glance cards -- a camera and the thermostat -- stacked in
 * one column; then the lit things; then the evening's two scenes as a card of
 * their own; then whatever is left. A row of equal boxes is a spreadsheet, and
 * the difference between that and a room is the one small column.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { cap, scenesFor, store, whatsOn } from '../store'
import type { Device, Room } from '../api'
import SceneBar from '../SceneBar.vue'
import CameraTile from '../tiles/CameraTile.vue'
import ClimateTile from '../tiles/ClimateTile.vue'
import LightTile from '../tiles/LightTile.vue'
import MediaTile from '../tiles/MediaTile.vue'
import PlainTile from '../tiles/PlainTile.vue'

/* woke: counts the times the panel has come back from rest, so the row can
   arrive again rather than only on the first load. `when` names the part of the
   day the scenes card serves, and comes from the arrangement above because that
   is where the clock already is. */
const props = defineProps<{ rooms: Room[]; when: string; woke?: number }>()

/* The row's cards, in the order drawn. A device is a card; the scenes are one
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

/* The row's edge fade is CSS where the browser can drive it from scroll. These
   two attributes are what is left over for CSS that cannot be: the fallback
   mask, which lifts an end that has nothing beyond it, and -- under glass -- the
   weather, which has to know the row has moved off home without being in the
   row to find out. Two toggleAttribute calls on a passive listener, so it is
   cheap enough to keep true on every browser rather than only the old ones. */
const bento = ref<HTMLElement | null>(null)
function edges() {
  const el = bento.value; if (!el) return
  el.toggleAttribute('data-at-start', el.scrollLeft <= 1)
  el.toggleAttribute('data-at-end', el.scrollLeft + el.clientWidth >= el.scrollWidth - 1)
}
onMounted(() => { edges(); bento.value?.addEventListener('scroll', edges, { passive: true }); addEventListener('resize', edges) })
onUnmounted(() => { bento.value?.removeEventListener('scroll', edges); removeEventListener('resize', edges) })

/*
 * The row arrives. On the first load, on waking from rest, and on coming back
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
let settle: number | undefined
function arrive() {
  if (empty.value) return                      // nothing to arrive, and an empty row must not be left at opacity 0
  /* Armed under reduced motion too. What arrives is not the same thing: panel.css
     cancels the travel there and leaves a 180ms fade, which is what the whole
     face collapses to. Arming it in both cases is what stops the two from
     drifting apart -- the decision about what a move becomes belongs in one
     place, and it is the stylesheet. */
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
  <slot name="quiet" v-else />
</template>
