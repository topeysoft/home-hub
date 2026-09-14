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
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ago, cap, done, justDone, scenesFor, store, whatsOn } from '../store'
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
/* A card here stands for something that is on, so turning it off would take it out of the row. It does
   not, and that is the rule this row is built around: a card you have just quieted KEEPS ITS PLACE --
   drained, saying what it now is and when -- until the panel looks away. A card going out from under
   the finger that touched it is the wrong answer to "did that work", and the row closing over the gap
   moves every other card under the hand as well. Tapping it again puts the thing back, which is where
   the undo lives now. store.ts (`done`) says what clears them; App.vue says when.

   The beat below is what is left for the other way a card can stop being on: a routine, or somebody in
   another room. Nobody's hand is on the screen for that one, so it reads itself off and goes.
   Held rather than computed, because a card keeping its place is the whole point, and a row rebuilt
   from what is still on has no place to keep. */
const SHOWN = 620, FADE = 340, SPARE = 90   // read the card off, fade it, and do not cut the fade short
const live = computed(() => whatsOn().filter(d => cap(d) !== 'camera' && cap(d) !== 'climate'))
const going = reactive<Record<string, true>>({})   // still in the row, on its way out
const gone = reactive<Record<string, true>>({})    // and now faded
const on = ref<Device[]>([])
function close(now: Device[]) {
  const rest = new Map(now.map(d => [d.id, d]))
  const kept: Device[] = []
  for (const d of on.value) {
    const still = rest.get(d.id)
    if (still) { kept.push(still); rest.delete(d.id) }
    else if (going[d.id] || done[d.id]) kept.push(d)
  }
  /* Kept cards this row has never held: Home was left and come back to while one was standing. They
     join at the end rather than being lost, so what you did is still here however you got back. */
  const held = new Set([...kept, ...rest.values()].map(d => d.id))
  const back = justDone().filter(d => !held.has(d.id) && cap(d) !== 'camera' && cap(d) !== 'climate')
  on.value = [...kept, ...rest.values(), ...back]
}
watch(live, (now, was) => {
  for (const d of was ?? []) {
    if (!now.some(x => x.id === d.id) && !going[d.id] && !done[d.id]) {
      going[d.id] = true                             // the class that arms the fade, with the card still at full strength
      /* Two frames before it goes, the same way the row's own entrance arms itself above: a class that
         both defines a transition and moves the value in one change cannot be relied on to animate. */
      window.setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(() => { gone[d.id] = true })), SHOWN)
      window.setTimeout(() => { delete going[d.id]; delete gone[d.id]; close(live.value) }, SHOWN + FADE + SPARE)
    }
  }
  close(now)
}, { immediate: true })
/* Swept: the panel looked away and the kept cards are not owed a place any more. No beat and no fade --
   the whole point of the moment is that there is nobody in front of it to see one. */
watch(() => Object.keys(done).length, () => close(live.value))
/* When a kept card was quieted, re-read on the half-minute so "just now" does not sit there for an hour.
   Only the WHEN: the card's own state line is already saying what it is, and a corner chip repeating
   "Off" next to the word Off is the kind of thing a wall panel has no room for. */
const tick = ref(Date.now())
let minute: number | undefined
onMounted(() => (minute = window.setInterval(() => (tick.value = Date.now()), 30000)))
onUnmounted(() => clearInterval(minute))
const keptLine = (d: Device) => done[d.id] && !live.value.some(x => x.id === d.id) ? ago(done[d.id].at / 1000, tick.value) : ''
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
      <component v-if="c.kind === 'device'" :is="tile(c.device!)" class="bento-card" :class="{ going: !!going[c.device!.id], gone: !!gone[c.device!.id], kept: !!keptLine(c.device!) }" :data-kept="keptLine(c.device!) || null" :style="{ '--flow-i': i }" :device="c.device!" v-hold="() => (store.opened = c.device!)" />
      <div v-else class="bento-card tile scene-card" :style="{ '--flow-i': i }">
        <span class="scene-card-when">{{ when }}</span>
        <SceneBar :room="null" />
      </div>
    </template>
  </div>
  <slot name="quiet" v-else />
</template>
