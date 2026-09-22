<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, notify, refreshStrip } from './store'
import { adoptStrip, stripCounted, dismissStrip, readStripOnce, stripAgain, stripDone, stripEnds, stripReach, stripRoom, stripSaw, stripWifi } from './api'
import Icon from './Icon.vue'
import StripArt from './StripArt.vue'
import { stripWaiting } from './adding'

/*
 * Setting a light strip up, on the wall.
 *
 * AN ARRIVAL, SO IT IS A SHEET, and it is deliberately the same shell, the same beats and the same
 * words as BridgeSheet: "That's the one" is the identity check here exactly as it is there and under
 * Add (design/adding/Words.dc.html). design/strip/Spine.dc.html is mostly a demonstration that a
 * strip needs no new flow at all -- four of its six beats are this sheet, unchanged.
 *
 * The two that are new are both here because NOTHING CAN BE READ BACK OFF A STRIP. The data line is
 * write-only on every one of these parts, so which order its colors come out in and how far it goes
 * are not detectable. Both are shown on the thing itself and named by the person looking at it, which
 * is the same move as pressing a switch to say which room it is in.
 *
 * The one thing this screen must never do is decide. Whether a strip is offering itself, which half
 * of the color question is live, and what the answers add up to are all the brain's (hub/strip.py);
 * the panel draws the state it is given and sends back what somebody said they could see.
 */
const b = computed(() => store.strip)
const busy = ref(false)
/* THE ONE LOCAL STEP, and the only one there should be. "No -- it's something else" does not tell the
   brain anything: it is the same question, with the yes/no swapped for the list of what else it could
   be. Nothing has been decided, the job is still `order`, and walking away leaves it exactly there. */
const other = ref(false)

const TITLE: Record<string, string> = {
  knocking: 'A light strip is here.',
  press: 'Press the button on it.',
  rhythm: 'How many times does it flash?',
  working: 'Setting it up.',
  order: 'Is it red?',
  length: 'How far does it go?',
  'order:colors': 'Are the colors right?',
  'length:length': 'Let’s measure it again.',
  'ready:colors': 'All set.',
  'ready:length': 'All set.',
  room: 'Where is it?',
  ready: 'It’s in.',
  failed: 'That did not work.',
  wifi: 'One thing it needs.',
}
const title = computed(() =>
  b.value?.needs === 'wifi' ? TITLE.wifi
  : b.value?.state === 'order' && (other.value || b.value?.asking === 'which') ? 'Then what is it showing?'
  : TITLE[`${b.value?.state}:${b.value?.revisit}`] ?? TITLE[b.value?.state ?? ''] ?? 'A light strip')

/* Somebody who came back to fix something already knows what a light strip is and what this screen
   does. Repeating the introduction at them is the panel forgetting it has met them. */
const back = computed(() => b.value?.revisit)
const lede = computed(() => {
  if (back.value === 'colors' && b.value?.state === 'order')
    return 'It is showing what it thinks red is. If that is not what you can see, the colors have been coming out in the wrong order.'
  if (back.value === 'length' && b.value?.state === 'length')
    return 'Filling up again, from the end it plugs in at. Tap when it reaches the far end of the strip as it is now.'
  return ''
})
/* THE LAST BEAT DOES NOT CLAIM THE ROOM IT HAS NOT GOT. Putting a light in a room needs the house
   to have made a device for it, and discovery is a moment behind the room chip -- in a real house on
   22 September it was more than twenty seconds behind, the placing was given up on, and this line
   said "in the room it lives in" anyway. The household read that, saw the light in the wrong place,
   and set the whole strip up again. The brain keeps the choice now (hub/strip.py `_owed`), so this
   only has to say which of the two is true. */
const finished = computed(() =>
  back.value === 'colors' ? 'Its colors are right now.'
  : back.value === 'length' ? 'It knows where it ends now.'
  : b.value?.placing ? `It is a light in the house now — on, dim, any color, on a schedule. It will be in ${b.value.placing} as soon as the house has finished noticing it.`
  : 'It is a light in the house now — on, dim, any color, on a schedule, in the room it lives in.')

/* ONE STEP, where a bridge has three. The hub does not hand over the Wi-Fi any more and never sees
   the password: commissioning carries it, encrypted, and does the letting-in at the same time. Two
   lines here would be a progress bar with nothing behind one of them. */
const STEPS = { letting: 'Letting it into the house' } as const
const ORDER = ['letting'] as const
const at = computed(() => ORDER.indexOf((b.value?.step ?? 'letting') as any))
const steps = computed(() => ORDER.map((id, i) => ({ id, text: STEPS[id], done: i < at.value, live: i === at.value })))
/* No progress bar. With one step it would sit at half for the whole wait and then vanish, which is
   a picture of progress rather than progress -- the very thing the one-step comment above objects to.
   The live dot says it is happening and does not claim to know how far along it is. */

/* What it could be showing, and the fourth one is not a color at all. A three-byte frame sent to a
   strip that carries a separate white channel misaligns by a byte a pixel and comes out as a repeating
   candy-stripe -- so "stripes" answers how many channels it has, which nobody has to be taught to see.
   "Nothing at all" is the only one that is a fault, and it goes somewhere else. */
type Pick = { id: string; name: string; sub?: string; show: 'red' | 'green' | 'blue' | 'stripes' | 'dark' }
const RED: Pick = { id: 'red', name: 'Red', show: 'red' }
const GREEN: Pick = { id: 'green', name: 'Green', show: 'green' }
const BLUE: Pick = { id: 'blue', name: 'Blue', show: 'blue' }
const STRIPES: Pick = { id: 'stripes', name: 'Stripes of color', sub: 'Not one color all along', show: 'stripes' }
const NOTHING: Pick = { id: 'nothing', name: 'Nothing at all', sub: 'Dark end to end', show: 'dark' }
/* Each question gets the set that is honest for IT, and both come to four.
   The first has already asked about red, so red is not offered as an answer to itself; stripes
   belongs here because this is where somebody would first notice it. The second is only ever reached
   by somebody who has already said it is not striped, so that choice is spent -- and red comes back,
   because the second frame makes a different byte loud and red is a real thing to see. */
const picks = computed(() => b.value?.asking === 'which'
  ? [RED, GREEN, BLUE, NOTHING]
  : [GREEN, BLUE, STRIPES, NOTHING])

async function run(fn: () => Promise<any>, after?: string) {
  if (busy.value) return
  busy.value = true
  try { store.strip = await fn(); if (after) notify(after) }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = false
  refreshStrip()
}
/* No code passed: a development board's is public and the brain fills it in. When real units
   exist this is where the one off the label goes. */
const adopt = () => run(() => adoptStrip())
const reach = () => run(stripReach)
const dismiss = () => run(dismissStrip)
const saw = (what: string) => { other.value = false; run(() => stripSaw(what)) }
const ends = () => run(stripEnds)
const again = () => run(stripAgain)
/* WHICH ONE WAS TAPPED, SAID AT ONCE AND BY THE THING THAT WAS TAPPED. The chips used to carry
   `busy` -- which every chip got, so the whole row dimmed together and none of them said "you
   picked me". They were also styled `chip`, which is the camera tile's status badge and not a
   button at all: no press state, because it was never meant to be pressed. This is `chip-btn`, the
   room picker the panel already uses for this same question under Add, and the answer is set before
   the request goes out, because the person has to see their own tap land. Nothing vanishes under
   the finger that touched it (AGENTS.md §4). */
const chose = ref('')
const room = (id: string) => { chose.value = id; run(() => stripRoom(id)) }

/* A PRESS, ON THE THING (design/door/PressIt.dc.html, design/strip/Press.dc.html). The one thing our
   own door asks, and there is nothing on this screen to do: the session is already open, the strip is
   lit, and the credentials are still on the hub because THE GATE IS ON THE STRIP. The wall waits and
   says it is waiting; the beat ends when the strip says it was touched, never on a timer here.

   FOUR COUNTS, READ OFF THE LIGHT, is the rung below (design/strip/ReachRhythm.dc.html) and is
   reached one way only: by saying the button cannot be reached. It shipped for a few hours as what
   everybody got, and counting four groups of flashes from across a room is a chore -- but it keeps a
   real secret behind SRP6a, which is why it is the fallback rather than deleted. A wrong answer is
   somebody having miscounted rather than having mistyped, which is why the sheet offers to start
   again rather than telling anybody off. */
const counts = ref<number[]>([0, 0, 0, 0])
const most = computed(() => b.value?.most ?? 6)
watch(() => b.value?.state, (now, was) => { if (now === 'rhythm' && was !== 'rhythm') counts.value = [0, 0, 0, 0] })
const bump = (i: number) => { counts.value[i] = counts.value[i] >= most.value ? 1 : counts.value[i] + 1 }
const counted = computed(() => counts.value.every(n => n >= 1))
const send = () => run(() => stripCounted(counts.value.join('')))

const ssid = ref(''), password = ref('')
const tell = () => {
  const name = ssid.value.trim()
  if (!name) return notify('Which Wi‑Fi? The name is needed.', 'error')
  run(() => stripWifi(name, password.value))
}

/* A finished job has nothing left to say once it has been read, and until the brain is told so it
   keeps reporting it -- the sheet goes away and the very next poll brings it straight back. Which
   states end a job is api.ts's to say, because it is a fact about the brain's machine. */
function close() {
  other.value = false
  const was = b.value?.state
  /* PUTTING A KNOCK DOWN IS NOT THROWING IT AWAY (design/knock/). A strip that is still asking goes
     back to being a line in the band and a dot on the + door, exactly as it was before anybody
     tapped -- so closing this is un-asking, and nothing of the strip's is forgotten. Blanking it
     here would take the line away too, and the strip is still in the room, still knocking.
     "Not mine" is how a household says they do not want it, and it is a button of its own. */
  store.stripAsked = false
  store.stripPutDown = true
  if (stripWaiting(was)) return
  if (store.strip) store.strip = { ...store.strip, state: 'none' }
  if (readStripOnce(was)) run(stripDone)
}
/* ESCAPE PUTS THIS DOWN AND NOTHING ELSE. This can be open over This house -- a knock opens it from
   Add -- and both listen on the window, so one press was closing the conversation AND throwing the
   household out of the page they opened it from. Captured, so it is answered before the page
   underneath hears it, and stopped there. */
function key(e: KeyboardEvent) {
  if (e.key !== 'Escape' || b.value?.state === 'working') return
  e.stopImmediatePropagation()
  close()
}
onMounted(() => window.addEventListener('keydown', key, true))
onUnmounted(() => window.removeEventListener('keydown', key, true))
</script>

<template>
  <div class="sheet-back" :class="{ 'over-panel': store.sheet }" v-if="b" @click.self="b.state === 'working' || close()">
    <div class="sheet strip" role="dialog" :aria-label="title">
      <div class="sheet-head">
        <h2 class="display">{{ title }}</h2>
        <button class="round sheet-close" v-if="b.state !== 'working'" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      </div>
      <div class="sheet-body">

        <!-- it has power and is saying hello. Nothing of the house's has gone anywhere yet, and the
             identity check is the object: it is two meters of lit strip and it is the only one lit. -->
        <template v-if="b.state === 'knocking'">
          <p class="sheet-lede">Something was plugged in nearby a moment ago. If it is a light strip of yours, it is the one that just came on.</p>
          <div class="stage">
            <StripArt show="lit" />
            <span class="caption"><span class="pulse-dot"></span>It is lit right now</span>
          </div>
          <div class="bridge-row">
            <span class="bridge-icon"><Icon name="lock" :size="18" /></span>
            <span class="bridge-text"><span class="bridge-name">Nothing has been let in yet</span><span class="bridge-sub">Until you say yes it is only knocking. Nothing of yours is on it.</span></span>
          </div>
          <div class="flow-actions">
            <button class="button" :class="{ busy }" @click="adopt">That’s the one</button>
            <button class="button ghost" @click="dismiss">Not mine</button>
          </div>
        </template>

<!-- OUR OWN DOOR, AND THE ONE THING IT ASKS. Not a code and nothing to count: press the button
             on the controller of the thing just unpacked (design/strip/Press.dc.html). A strip that
             came through Matter's door never reaches this. -->
        <template v-else-if="b.state === 'press'">
          <p class="sheet-lede">The button is on the controller, at the end it plugs in at. A short press, and it is yours — there is nothing to read, count or type.</p>
          <div class="stage">
            <StripArt show="lit" />
            <span class="caption">It is lit, steady, so you can see which one you have</span>
          </div>
          <p class="waiting"><span class="pulse-dot"></span>Waiting for the press…</p>
          <div class="flow-actions">
            <button class="button ghost wide" :class="{ busy }" @click="reach">It has no button I can reach</button>
          </div>
        </template>

        <!-- THE RUNG BELOW, and the only way here is the button above (design/strip/ReachRhythm.dc.html). -->
        <template v-else-if="b.state === 'rhythm'">
          <p class="sheet-lede">It has started flashing in four groups, over and over. Count each group and tap the numbers. There is still nothing to read off a label.</p>
          <div class="stage">
            <StripArt show="lit" />
            <span class="caption"><span class="pulse-dot"></span>Watch it, then tap what you counted</span>
          </div>
          <div class="rhythm-row">
            <button v-for="(n, i) in counts" :key="i" class="rhythm-count" :class="{ set: n >= 1 }"
                    @click="bump(i)" :aria-label="`Group ${i + 1}, ${n || 'not counted'}`">
              <span class="rhythm-n">{{ n || '–' }}</span>
              <span class="rhythm-sub">{{ n === 1 ? 'flash' : 'flashes' }}</span>
            </button>
          </div>
          <div class="flow-actions">
            <button class="button" :class="{ busy }" :disabled="!counted" @click="send">That’s it</button>
            <button class="button ghost" @click="dismiss">I can’t see it either</button>
          </div>
        </template>

        <!-- it needs the one thing the hub cannot know for a thing it has never met -->
        <template v-else-if="b.needs === 'wifi'">
          <p class="sheet-lede">{{ b.text || 'It needs the house’s Wi‑Fi. Tell it once; nothing after this asks again.' }}</p>
          <label class="field"><span class="field-label">Wi‑Fi name</span><input class="input" v-model="ssid" autocomplete="off" autocapitalize="off" spellcheck="false" @keydown.enter="tell" /></label>
          <label class="field"><span class="field-label">Password</span><input class="input" type="password" v-model="password" autocomplete="off" @keydown.enter="tell" /></label>
          <div class="flow-actions">
            <button class="button" :class="{ busy }" @click="tell">Continue</button>
            <button class="button ghost" @click="close">Not now</button>
          </div>
        </template>

        <!-- the hub is talking to it over Bluetooth. Nothing to do, so nothing to press. -->
        <template v-else-if="b.state === 'working'">
          <p class="sheet-lede">It is being let in now, over Bluetooth, and it gets onto your Wi‑Fi as part of the same conversation. A moment. You can walk away; the wall will say when it is done.</p>
          <div class="stage"><StripArt show="lit" /></div>
          <ul class="bridge-steps">
            <li v-for="s in steps" :key="s.id" :class="{ done: s.done, live: s.live }">
              <span class="bridge-tick"><Icon v-if="s.done" name="check" :size="13" /><span v-else-if="s.live" class="pulse-dot"></span></span>
              <span>{{ s.text }}</span>
            </li>
          </ul>
        </template>

        <!-- WHICH COLOR COMES OUT FIRST. Strips do not agree and nothing can be read back off one, so
             it is lit and the household names what they see. design/strip/Order.dc.html -->
        <template v-else-if="b.state === 'order' && !other && b.asking === 'red'">
          <p class="sheet-lede">{{ lede || 'Strips do not all put their colors in the same order, and there is no way to ask one. So: look at it.' }}</p>
          <div class="stage">
            <StripArt show="red" />
            <span class="caption">All of it, one color</span>
          </div>
          <div class="flow-actions">
            <button class="button" :class="{ busy }" @click="saw('red')">Yes, that’s red</button>
            <button class="button ghost" @click="other = true">No — it’s something else</button>
          </div>
        </template>

        <!-- whatever they are looking at IS the answer -->
        <template v-else-if="b.state === 'order'">
          <p class="sheet-lede">Whatever you are looking at is the answer. Tap it and the strip is right from then on.</p>
          <ul class="picks">
            <li v-for="p in picks" :key="p.id">
              <button class="pick" :class="{ busy }" @click="saw(p.id)">
                <StripArt :show="p.show" />
                <span class="bridge-name">{{ p.name }}</span>
                <span class="bridge-sub" v-if="p.sub">{{ p.sub }}</span>
              </button>
            </li>
          </ul>
        </template>

        <!-- HOW FAR IT GOES. It fills from the plug end; the moment the far end lights, the picture
             stops changing, and that is the thing a person can catch. design/strip/Fill.dc.html -->
        <template v-else-if="b.state === 'length'">
          <p class="sheet-lede">{{ lede || 'It is lighting up one at a time, from the end it plugs in at. Tap the moment the far end of your strip comes on.' }}</p>
          <div class="stage">
            <StripArt show="fill" />
            <span class="ends"><span>Where it plugs in</span><span>… still dark, still filling</span></span>
            <span class="caption"><span class="pulse-dot"></span>Missed it? It empties and fills again, as many times as you need</span>
          </div>
          <div class="flow-actions stack">
            <button class="button wide" :class="{ busy }" @click="ends">That’s the whole of it</button>
            <button class="button ghost wide" @click="again">Start again</button>
          </div>
        </template>

        <!-- the ordinary room chips every other new device gets. Nothing here is invented. -->
        <template v-else-if="b.state === 'room'">
          <p class="sheet-lede">That is the only thing left to say. It is lit, all of it, and it is yours.</p>
          <div class="stage"><StripArt show="lit" /></div>
          <div class="press-rooms">
            <button class="chip-btn" v-for="r in b.rooms ?? []" :key="r.id" :class="{ on: chose === r.id }"
                    :aria-pressed="chose === r.id" @click="room(r.id)">{{ r.name }}</button>
          </div>
        </template>

        <template v-else-if="b.state === 'ready'">
          <p class="flow-done">
            <span class="done-icon"><Icon name="check" :size="20" /></span>
            <span>{{ finished }}</span>
          </p>
          <div class="flow-actions"><button class="button" @click="close">Done</button></div>
        </template>

        <!-- It did not work, in the brain's words and never a library's. The brain's sentence must
             not open the way the title does: the first one to reach a screen began "That did not
             work." under a heading reading "That did not work." -->
        <template v-else>
          <p class="sheet-lede">{{ b.text || 'The hub could not finish setting it up.' }}</p>
          <div class="flow-actions"><button class="button ghost" @click="close">Not now</button></div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Scoped rather than added to panel.css: every name in here is about a strip and nothing else draws
   one, and panel.css is a flat global sheet where a repeated class silently restyles the other
   component (AGENTS.md §4). NetworkSheet.vue does the same for the same reason. */
.stage {
  position: relative; padding: 46px 22px 40px; margin-bottom: 18px;
  border-radius: var(--r-lg); background: rgba(255, 255, 255, .03);
  border: 1px solid var(--edge); overflow: hidden;
}
.ends {
  display: flex; justify-content: space-between; margin-top: 12px;
  font-size: 13px; color: var(--muted);
}
.caption {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  margin-top: 26px; font-size: 13px; color: var(--muted); text-align: center;
}
.picks { list-style: none; margin: 0 0 4px; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pick {
  width: 100%; display: flex; flex-direction: column; gap: 10px; text-align: left;
  padding: 16px 16px 15px; border-radius: var(--r-md);
  background: var(--surface); border: 1px solid var(--edge); color: var(--ink);
}
.pick:active { background: var(--surface-press); }
/* The room chips are `press-rooms`, which is the picker Add already uses for this same question --
   not a row of this screen's own. This used to be a `.rooms` block here, and `.rooms` in panel.css
   is THE ROOMS TAB's container: `flex-direction: column`. A scoped block only overrides what it
   names, so the wrap here was set and the direction came from the other screen, and every room in
   the house was a full-width row. In a house with twenty-three of them that is the whole sheet.
   AGENTS.md §4, and lint:css cannot see this one because the two blocks are not both in panel.css. */
.button.wide { width: 100%; }
/* a full-width primary with a small ghost beside it reads as an orphan, so they stack */
.flow-actions.stack { flex-direction: column; align-items: stretch; }
/* The line that says nothing is happening yet, and that nothing is meant to be. It sits between the
   strip and the only button, where a primary would be on every other beat -- because on this one the
   thing to press is not on the wall. */
.waiting {
  display: flex; align-items: center; justify-content: center; gap: 9px;
  margin: 0 0 16px; font-size: 13.5px; color: var(--ink-2);
}
</style>
