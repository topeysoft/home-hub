<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * A light, opened: the two things a lamp physically is, and the three it is used at.
 *
 * The columns are 168 and 126 wide because the hand that reaches for them is not looking — this is
 * a panel on a wall, and the 4px range input the pane used to carry could only be hit by someone
 * standing in front of it with a mouse. The three cards are for everyone who will never drag
 * anything: each one is a brightness the house can already send.
 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { Device } from '../api'
import { keepColor, listStrips, revisitStrip, tuneStrip, tuneStripBy, tuneStripDone, type StripRow } from '../api'
import { BEFORE, FIRST, gap, step } from '../walk'
import { guessNow, isDead, notify, perform, roomOf, store } from '../store'
import { COLORS, WHITES, autoKelvin, dataFor, guessFor, handlesOf, hsRgb, same, swatchCss, wantedOf, wantedRgb, type Wanted } from '../color'
import { rgb } from '../sky'
import Icon from '../Icon.vue'
import { useNarrow, useSlide } from './slide'

const props = defineProps<{ device: Device }>()
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const on = computed(() => props.device.state === 'on')
const pct = computed(() => on.value && a.value.brightness != null ? Math.round((a.value.brightness / 255) * 100) : on.value ? 100 : 0)
const dimmable = computed(() => 'brightness' in (a.value ?? {}) || (a.value.supported_color_modes ?? []).some((m: string) => m !== 'onoff'))

/* What white the lamp is on, if it is on one. This used to drive a Warmth column,
   and the column asked for color_temp_kelvin -- so it DISAPPEARED the moment a
   bulb went into a color mode, taking the only way back to white with it. The
   whites are four swatches in the color block now; this is all that is left of
   it, and it says only whether the bulb has a white to speak of. */
const kelvin = computed(() => a.value.color_temp_kelvin as number | undefined)

/*
 * WHAT COLOR IT IS, and the three ways to say so. color.ts has the vocabulary and
 * the argument; this is the pane's half of it.
 *
 * `canWhite` and `canColor` are asked separately because a house is full of bulbs
 * that can do one and not the other. A lamp with neither gets no color block at
 * all rather than a row of controls that do nothing -- the same rule the Warmth
 * column was already written to, only now it is the whole block that is absent
 * instead of a control that comes and goes with the bulb's MODE.
 */
const COLOR_MODES = ['hs', 'rgb', 'rgbw', 'rgbww', 'xy']
const modes = computed(() => (a.value.supported_color_modes ?? []) as string[])
const canColor = computed(() => modes.value.some(m => COLOR_MODES.includes(m)))
const canWhite = computed(() => modes.value.includes('color_temp') || kelvin.value != null)
const hasColor = computed(() => canColor.value || canWhite.value)

const autoK = computed(() => autoKelvin(store.sky.elevation))
const wanted = computed(() => wantedOf(a.value))
/* a swatch is a LABEL for a color, drawn at one lightness across the wheel so the
   row reads as a set; anything standing for the actual lamp uses the real sRGB */
const swatch = (w: Wanted) => w.kind === 'color' ? swatchCss(w.hue, w.amount) : rgb(wantedRgb(w, autoK.value))
const chosen = (w: Wanted) => same(wanted.value, w)

async function choose(w: Wanted) {
  if (dead.value) return
  try { await perform(props.device, 'on', dataFor(w, autoK.value), { state: 'on', attrs: guessFor(w, autoK.value) }) }
  catch (e: any) { notify(e.message, 'error') }
}

/*
 * MORE COLORS: two columns, for the color that is not one of the twelve and for
 * the one that is but does not look like it on this particular bulb. A lamp's
 * idea of pink is not the swatch's pink, so what is being done here is matching
 * against the thing glowing in the room rather than picking out of a space --
 * which is why the head shows what the lamp is showing NOW.
 *
 * Two columns rather than a disc, and the reason is this pane's own: its columns
 * are 168 wide because the hand that reaches for them is not looking. A dot on a
 * disc has to be aimed, two axes at once, standing in front of a wall. Two drags,
 * each in one direction, is the gesture this pane already teaches for brightness.
 *
 * The house is told on the way UP only, as everything else here is -- see
 * slide.ts: forty service calls to a Zigbee lamp is how a bulb falls off a mesh.
 * So a match is made by nudging and letting go, watching the lamp, nudging again.
 */
const tuning = ref(false)
const tune = reactive({ hue: 32, amount: 60 })
watch(tuning, (on) => { if (on) Object.assign(tune, handlesOf(wanted.value)) })
watch(() => props.device.id, () => (tuning.value = false))
const tuneRgb = computed(() => rgb(hsRgb(tune.hue, tune.amount)))
function sendTune() { choose({ kind: 'color', hue: tune.hue, amount: tune.amount }) }

/* KEEP IT. A color matched by eye against the lamps in this room is worth more than
   any preset, and making somebody find it twice is the real failure. Kept on the
   ROOM rather than the lamp: it was tuned against the bulbs in there, and the one
   beside it is the same make more often than not. */
const room = computed(() => roomOf(props.device))
const kept = computed<{ hue: number; amount: number }[]>(() =>
  (room.value?.colors ?? []).map(([hue, amount]) => ({ hue, amount })))
const alreadyKept = computed(() => kept.value.some(c => same(c && { kind: 'color', ...c }, { kind: 'color', hue: tune.hue, amount: tune.amount })))
const keeping = ref(false)
async function keep() {
  const r = room.value
  if (!r || keeping.value || alreadyKept.value) return
  keeping.value = true
  try { r.colors = await keepColor(r.id, Math.round(tune.hue), Math.round(tune.amount)) }
  catch (e: any) { notify(e.message, 'error') }
  keeping.value = false
}

async function bright(v: number) {
  const p = Math.max(1, Math.min(100, v))
  if (!await perform(props.device, 'on', { brightness_pct: p }, { state: 'on', attrs: { brightness: Math.round(p * 2.55) } })) return
}
/* while a finger is down the drawing moves and the house is left alone; see panes/slide.ts */
const guess = computed({
  get: () => pct.value,
  set: (v: number) => guessNow(props.device, { state: on.value ? undefined : 'on', attrs: { brightness: Math.round(v * 2.55) } }),
})
/* the two tuning drags, in the same shape as brightness: the drawing moves under
   the finger, the lamp is told on the way up. `hue` is 0-100 of the wheel here
   because that is what a column is -- levelFrom knows nothing about degrees. */
const hueSlide = useSlide({
  vertical: () => !narrow.value,
  live: v => (tune.hue = v * 3.6),
  settle: v => { tune.hue = v * 3.6; sendTune() },
})
const amtSlide = useSlide({
  vertical: () => !narrow.value,
  live: v => (tune.amount = v),
  settle: v => { tune.amount = v; sendTune() },
})

/* TWO THINGS THAT WERE SETTLED ONCE AND GO STALE (design/strip/Later.dc.html).
 *
 * A strip gets cut down to fit a shelf. Another gets soldered on to reach round a corner. One fails
 * and is replaced by whatever was in stock, which is very often not the same make and so not the same
 * channel order. None of that is unusual and none of it should mean setting the thing up again -- so
 * each row is the setup question it came from, reopened, and nothing else.
 *
 * Everything above them is the ordinary light pane with no idea this is a strip, which is the point:
 * the board's whole argument is that a strip is an ordinary light with two extra rows at the foot.
 * Note what is NOT here -- no effects, no segments, no zones. A strip with a hundred named animations
 * is a maker's toy; this is an accent light a household should be able to forget about.
 */
const strip = ref<StripRow | null>(null)
onMounted(async () => {
  // A hub too old to know what a strip is answers 404 and the rows simply never appear.
  try {
    const rows = (await listStrips()).strips
    strip.value = rows.find(r => r.device && r.device === props.device.hw) ?? null
  } catch { strip.value = null }
})
/* LEDs are sold by the metre and bought by the metre, so the length is said in metres even though
   what was measured is lights. Sixty to the metre is the common density and this says "about". */
const metres = computed(() => {
  /* While the end is being walked this says where it is NOW, not where it was when the door opened:
     it is the same fact the row already carries, and a control whose only feedback is two metres of
     wall behind a television is a control somebody presses twice. */
  const n = moving.value ? endsAt.value : strip.value?.count
  return n ? `About ${(n / 60).toFixed(1)} m` : 'Measured once'
})
/* THE PICTURE, AND WHAT ITS SCALE IS. The bar is a five-metre reel -- what these are sold on -- and
   the lit part is what the hub drives. So the dark end is real: it is the stretch of strip somebody
   would have left dark by tapping early, which is the failure this door exists to fix. A strip
   longer than a reel fills it rather than overflowing. */
const REEL = 300
/* While the end is being walked the PICTURE moves and the number does not: the strip is the thing to
   look at, and a count of lights on the wall is what the fill was designed to avoid (Nudge). The
   metres are said again once the answer is kept. */
const lit = computed(() => {
  const n = (moving.value ? endsAt.value : strip.value?.count) ?? 0
  return `${Math.max(6, Math.min(100, Math.round((n / REEL) * 100)))}%`
})
const asking = ref(false)
async function askAgain(what: 'colors' | 'length') {
  if (!strip.value || asking.value) return
  asking.value = true
  try { store.strip = await revisitStrip(strip.value.id, what) }
  catch (e: any) { notify(e.message, 'error') }
  asking.value = false
}

/* ONE DOOR FOR BOTH, BECAUSE NEITHER IS USED OFTEN (design/strip/OneDoor.dc.html, chosen 22
 * September). The length and the color order are asked once and then left alone for a year, and two
 * rows across the foot of the rig gave them the width of the thing the pane is actually for. One
 * row now, under the three, drawing the strip rather than wearing an icon -- and both questions
 * live behind it, on the sheet design/strip/Behind.dc.html draws. */
const door = ref(false)

/* MOVING THE END, WITH THE STRIP IN FRONT OF YOU (design/strip/Nudge.dc.html).
 *
 * The fill at setup is a measurement and its error is somebody's reaction time, so it lands a few
 * lights either side. Long is invisible -- the surplus falls off the wire -- and short leaves the
 * far end dark for ever, which is the one that gets reported. This is the other half of what was
 * decided on 20 September: the fill while somebody is standing there, and this for ever after.
 *
 * The strip lights to the length it believes with a cool tail on the last few, because at sixty
 * lights to the metre a warm lit strip is a glow and its end is a guess. Nothing is written down
 * until "That's it": holding a button must not spend an NVS erase cycle a frame. */
const moving = ref(false)
const endsAt = ref(0)
const movingBusy = ref(false)

/* The sheet opens with the strip already lit to the length it believes, which is what the board
   draws and the reason somebody opened this door: you came to look at the end. A strip that cannot
   be reached says so by leaving the card a picture with nothing to press. */
async function openDoor() {
  if (!strip.value || asking.value) return
  door.value = true
  if (!strip.value.online) return
  asking.value = true
  try {
    const t = await tuneStrip(strip.value.id)
    endsAt.value = t.count
    moving.value = true
  } catch (e: any) { notify(e.message, 'error') }
  asking.value = false
}
/* Closing the door puts the strip back to being a light and keeps what it was walked to. */
async function closeDoor() {
  if (moving.value) await closeTune(true)
  door.value = false
}
/* One request at a time and never a queue: a held button that outruns the hub would leave the wall
   counting lights the strip never went to, and the strip is the thing being looked at. A step that
   arrives while one is in flight is DROPPED, not deferred -- so a slow hub walks the end more
   slowly rather than lurching when it catches up, which is the behavior worth having when somebody
   is watching the strip and not the screen. */
async function moveBy(by: number) {
  if (!strip.value || movingBusy.value) return
  movingBusy.value = true
  try {
    const t = await tuneStripBy(strip.value.id, by)
    endsAt.value = t.count
  } catch (e: any) { notify(e.message, 'error') }
  movingBusy.value = false
}
async function closeTune(keep: boolean) {
  const id = strip.value?.id
  moving.value = false
  stopWalk()
  if (!id) return
  try {
    const t = await tuneStripDone(id, keep)
    if (strip.value) strip.value = { ...strip.value, count: t.count }
  } catch (e: any) { notify(e.message, 'error') }
}

/* A tap is one light; a hold walks, slowly at first so one light is still reachable by holding a
   moment too long. The numbers are walk.ts's and are pinned by a test. */
let walkTimer: number | undefined
let walkStep = 0
function startWalk(by: number) {
  stopWalk()
  moveBy(by * FIRST)
  walkStep = 0
  const next = (wait: number) => {
    walkTimer = window.setTimeout(() => {
      moveBy(by * step(walkStep))
      walkStep++
      next(gap(walkStep))
    }, wait)
  }
  next(BEFORE)
}
function stopWalk() { clearTimeout(walkTimer); walkTimer = undefined }
onUnmounted(stopWalk)
/* A strip that goes away mid-tune must not leave the pane pretending, and a pane that is closed on
   a different device must not leave a strip wearing its tail. */
watch(() => props.device.id, () => { if (moving.value) closeTune(true); door.value = false })
/* The colors question hands the whole screen to the setup sheet, so the door gets out of its way. */
watch(() => store.strip, s => { if (s) door.value = false })

const narrow = useNarrow()          // a phone drags the same two things on their sides
const dim = useSlide({ vertical: () => !narrow.value, live: v => (guess.value = v), settle: v => bright(v) })
const along = (p: number) => narrow.value ? { width: p + '%' } : { height: p + '%' }
const mark = (p: number) => narrow.value ? { left: p + '%' } : { bottom: p + '%' }

/* The three a lamp is actually used at. Fixed for now and deliberately few; what they should
   eventually be is what THIS lamp keeps being set to, which the event log already knows. */
const LEVELS = [
  { id: 'read', name: 'Reading', sub: 'Bright, and cooler', icon: 'sun', pct: 100, k: 4000 },
  { id: 'evening', name: 'Evening', sub: 'Low and warm', icon: 'light', pct: 35, k: 2700 },
  { id: 'night', name: 'Night', sub: 'Enough to see by', icon: 'moon', pct: 5, k: 2200 },
]
const here = computed(() => {
  if (!on.value) return ''
  return LEVELS.reduce((best, l) => Math.abs(l.pct - pct.value) < Math.abs(best.pct - pct.value) ? l : best).id
})
async function level(l: typeof LEVELS[number]) {
  if (dead.value) return
  const data: Record<string, unknown> = dimmable.value ? { brightness_pct: l.pct } : {}
  /* A preset is a BRIGHTNESS the house is used to, and it used to carry a color
     temperature with it unconditionally. On a lamp somebody had set to pink that
     quietly turned it white, with nothing on the screen having said it would --
     the same mode leak the Warmth column had, wearing a different hat. A light
     with a color of its own keeps it; one on Automatic or on a white still gets
     the temperature, because for those the preset IS the whole answer. */
  const keepsColor = wanted.value.kind === 'color'
  if (canWhite.value && !keepsColor) data.color_temp_kelvin = l.k
  try { await perform(props.device, 'on', data, { state: 'on', attrs: { brightness: Math.round(l.pct * 2.55), ...(canWhite.value && !keepsColor ? { color_temp_kelvin: l.k } : {}) } }) }
  catch (e: any) { notify(e.message, 'error') }
}
</script>

<template>
  <div class="rig rig-light" :class="{ 'rig-has-strip': !!strip }">
    <div class="rig-slot" v-if="dimmable">
      <div class="rig-col" role="slider" tabindex="0" :aria-label="`${device.name} brightness`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="pct"
           :class="{ held: dim.held.value, dead, bar: narrow }" @pointerdown="dim.down" @pointermove="dim.move" @pointerup="dim.up" @pointercancel="dim.cancel"
           @keydown="e => dim.key(e, pct)">
        <span class="rig-fill" :style="along(on ? Math.max(pct, 2) : 0)"></span>
        <span class="rig-mark" :style="mark(pct)" v-if="on"></span>
        <span class="rig-end top"><Icon name="sun" :size="21" /></span>
        <span class="rig-end bottom" :class="{ lit: on && pct > 12 }"><Icon name="moon" :size="19" /></span>
      </div>
      <span class="rig-lbl">Brightness</span>
    </div>

    <!-- EVERYTHING THAT IS NOT THE BRIGHTNESS COLUMN, in a column of its own: the light's own two
         questions on the first line, and under them, on the right, the one row a strip adds. The
         wrapper is what lets the strip's row start at the colors' left edge instead of running the
         whole width of the rig under a column it has nothing to do with -- and it is what puts the
         brightness column back to the full height it has on every other light's pane.
         design/strip/OneDoor.dc.html. -->
    <div class="rig-rest">
    <div class="rig-line">

    <!-- WHAT COLOR IT IS. This replaces the Warmth column, which asked for
         color_temp_kelvin and so VANISHED the moment a bulb went into a color
         mode -- Home Assistant's modes showing through a panel whose job is to
         hide them, and no way back to white once a lamp was pink. Here white is
         a swatch beside the colors, so nothing appears or disappears and the way
         back is where it always was. design/device page 4. -->
    <div class="rig-color" v-if="hasColor && !tuning">
      <!-- no label over the pill: Automatic is not a color, it is the absence of
           one, and it says what it is on itself. The labels start at the swatches. -->
      <button class="rig-auto" :class="{ on: chosen({ kind: 'auto' }) }" :disabled="dead" @click="choose({ kind: 'auto' })">
        <span class="rig-auto-dot" aria-hidden="true"></span>
        <span class="rig-auto-text">
          <span class="rig-auto-name">Automatic</span>
          <span class="rig-auto-sub">Follows the light</span>
        </span>
        <Icon v-if="chosen({ kind: 'auto' })" name="check" :size="18" class="rig-auto-tick" />
      </button>
      <!-- ONE GRID, UNDER ONE LABEL (design/strip/Both.dc.html, chosen 22 September). The kept
           colors, the twelve and the whites were three blocks with a label and two gaps each, and on
           a light that can do both -- in a room with colors kept in it -- the block came to 512px
           where the rig has about 426 to give. What was under it went off the bottom of a 1440 wall.

           It is the same argument this block was built on, taken one step further: a white is a
           swatch beside the colors rather than a mode, so nothing appears or disappears and the way
           back is where it was. A kept color is no different. The kept ones come first because they
           are this room's, and they are the ones a hand is reaching for. -->
      <span class="rig-lbl">Colors</span>
      <div class="rig-swatches">
        <button v-for="c in kept" :key="`k${c.hue}-${c.amount}`" class="rig-swatch" :class="{ on: chosen({ kind: 'color', ...c }) }"
                :style="{ background: swatch({ kind: 'color', ...c }) }" :disabled="dead"
                :aria-label="`Kept color, hue ${c.hue}`" :aria-pressed="chosen({ kind: 'color', ...c })"
                @click="choose({ kind: 'color', ...c })"></button>
        <template v-if="canColor">
          <button v-for="c in COLORS" :key="c.hue" class="rig-swatch" :class="{ on: chosen({ kind: 'color', ...c }) }"
                  :style="{ background: swatch({ kind: 'color', ...c }) }" :disabled="dead"
                  :aria-label="`Color, hue ${c.hue}`" :aria-pressed="chosen({ kind: 'color', ...c })"
                  @click="choose({ kind: 'color', ...c })"></button>
        </template>
        <template v-if="canWhite">
          <button v-for="k in WHITES" :key="k" class="rig-swatch white" :class="{ on: chosen({ kind: 'white', kelvin: k }) }"
                  :style="{ background: swatch({ kind: 'white', kelvin: k }) }" :disabled="dead"
                  :aria-label="`White, ${k} kelvin`" :aria-pressed="chosen({ kind: 'white', kelvin: k })"
                  @click="choose({ kind: 'white', kelvin: k })"></button>
        </template>
      </div>
      <button class="rig-more" v-if="canColor" :disabled="dead" @click="tuning = true">More colors</button>
    </div>

    <!-- and the thirteenth: not a picker with a preview, a pair of dials turned
         while looking at the lamp. What it is showing NOW sits at the top. -->
    <div class="rig-tune" v-if="hasColor && tuning">
      <div class="rig-tune-head">
        <button class="rig-back" @click="tuning = false"><Icon name="back" :size="17" /> Colors</button>
        <span class="rig-tune-now" :style="{ background: tuneRgb }" aria-hidden="true"></span>
        <span class="rig-tune-text">
          <span class="rig-auto-name">On the lamp now</span>
          <span class="rig-auto-sub">Nudge until it matches the room</span>
        </span>
      </div>
      <div class="rig-slot">
        <div class="rig-col rig-hue" :class="{ bar: narrow }" role="slider" tabindex="0" :aria-label="`${device.name} hue`"
             aria-valuemin="0" aria-valuemax="360" :aria-valuenow="Math.round(tune.hue)"
             @pointerdown="hueSlide.down" @pointermove="hueSlide.move" @pointerup="hueSlide.up" @pointercancel="hueSlide.cancel"
             @keydown="e => hueSlide.key(e, Math.round(tune.hue / 3.6))">
          <span class="rig-handle" :style="mark(tune.hue / 3.6)"></span>
        </div>
        <span class="rig-lbl">Hue</span>
      </div>
      <div class="rig-slot">
        <div class="rig-col rig-amount" :class="{ bar: narrow }" role="slider" tabindex="0" :aria-label="`${device.name} amount of color`"
             aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(tune.amount)"
             :style="{ '--tune': tuneRgb }"
             @pointerdown="amtSlide.down" @pointermove="amtSlide.move" @pointerup="amtSlide.up" @pointercancel="amtSlide.cancel"
             @keydown="e => amtSlide.key(e, Math.round(tune.amount))">
          <span class="rig-handle" :style="mark(tune.amount)"></span>
        </div>
        <span class="rig-lbl">Amount</span>
      </div>
      <!-- A row of its own under the columns, not a column beside them. The board
           drew this pane 880 wide and the real one gives the rig 694: two 168px
           columns and a brightness leave about 140px, which is a card one word to
           a line. Across the bottom it has the whole width and costs the columns
           seventy pixels they can spare. -->
        <button class="rig-keep-card" :class="{ on: alreadyKept }" :disabled="dead || keeping || alreadyKept" @click="keep">
          <span class="rig-keep-dot" :style="{ background: tuneRgb }" aria-hidden="true"></span>
          <span class="rig-auto-text">
            <span class="rig-auto-name">{{ alreadyKept ? 'Kept for this room' : 'Add to this room' }}</span>
            <span class="rig-auto-sub">{{ alreadyKept ? 'One tap in Colors' : 'One tap next time' }}</span>
          </span>
        </button>
    </div>


    <div class="rig-levels" v-if="!tuning">
      <span class="rig-lbl">The three it is used at</span>
      <button v-for="l in LEVELS" :key="l.id" class="rig-card" :class="{ on: here === l.id }" :disabled="dead" @click="level(l)">
        <span class="rig-card-icon"><Icon :name="l.icon" :size="18" /></span>
        <span class="rig-card-text">
          <span class="rig-card-name">{{ l.name }}</span>
          <span class="rig-card-sub">{{ here === l.id ? 'Where it is now' : l.sub }}</span>
        </span>
      </button>
    </div>

    </div>

    <!-- ONE ROW, AND IT IS THE ONLY PART OF THIS PANE THAT KNOWS WHAT A STRIP IS. Both questions
         behind it: neither is used more than once a year, and two rows across the foot gave them the
         width of the thing the pane is for. It draws the strip rather than wearing an icon, because
         a picture of the thing behind the television is what tells somebody what this row is.
         design/strip/OneDoor.dc.html, chosen 22 September. -->
    <div class="rig-ask" v-if="strip && !tuning">
      <span class="rig-lbl">Because it is a strip</span>
      <button class="rig-card sd-door" :disabled="dead || asking" @click="openDoor()">
        <span class="rig-card-icon"><Icon name="pin" :size="18" /></span>
        <span class="rig-card-text">
          <span class="rig-card-name">Set up as a strip <em>{{ metres }}</em></span>
          <span class="rig-card-sub">How long it is, and how its colors come out.</span>
        </span>
        <span class="sd-strip" aria-hidden="true"><i :style="{ width: lit }"></i></span>
        <Icon name="back" :size="18" class="sd-chev" />
      </button>
    </div>
    </div>
  </div>

  <!-- WHAT IS BEHIND THE DOOR (design/strip/Behind.dc.html). The setup conversation reopened and
       nothing more: no effects, no segments, no zones. The length is walked here rather than
       measured again from nothing -- "Measure it again" is still the way back to the fill for the
       household who cut a metre off -- and the colors question hands over to the sheet it came
       from, which is the screen that asks it properly. -->
  <div class="sheet-back" v-if="door" @click.self="closeDoor()">
    <div class="sheet sd-sheet" role="dialog" aria-label="Set up as a strip">
      <div class="sheet-head">
        <h2 class="display">Set up as a strip</h2>
        <button class="round sheet-close" aria-label="Close" @click="closeDoor()"><Icon name="close" :size="20" /></button>
      </div>
      <div class="sheet-body">
        <p class="sheet-lede">Two things this was told once, and both of them go stale. A strip gets cut down, joined onto, or replaced by one that is not the same make.</p>

        <div class="sd-card" :class="{ on: moving }">
          <div class="sd-card-head">
            <span class="rig-card-icon"><Icon name="pin" :size="18" /></span>
            <span class="rig-card-text">
              <span class="rig-card-name">Ends here <em>{{ metres }}</em></span>
              <span class="rig-card-sub">{{ moving ? 'Move it until the light stops where the strip stops.' : 'The strip cannot be reached, so it cannot be walked just now.' }}</span>
            </span>
          </div>
          <span class="sd-strip wide" aria-hidden="true"><i :style="{ width: lit }"></i></span>
          <template v-if="moving">
            <div class="sd-row">
              <button class="sd-step" :disabled="endsAt <= 1"
                      @pointerdown="startWalk(-1)" @pointerup="stopWalk" @pointerleave="stopWalk" @pointercancel="stopWalk">
                <Icon name="minus" :size="16" /> Shorter
              </button>
              <button class="sd-step"
                      @pointerdown="startWalk(1)" @pointerup="stopWalk" @pointerleave="stopWalk" @pointercancel="stopWalk">
                <Icon name="plus" :size="16" /> Longer
              </button>
            </div>
            <div class="sd-row">
              <button class="button" @click="closeTune(true); door = false">That’s it</button>
              <button class="button ghost" @click="closeTune(false); askAgain('length')">Measure it again</button>
            </div>
          </template>
        </div>

        <button class="sd-card sd-tap" :disabled="asking || !strip?.online" @click="askAgain('colors')">
          <span class="sd-card-head">
            <span class="rig-card-icon"><Icon name="light" :size="18" /></span>
            <span class="rig-card-text">
              <span class="rig-card-name">The colors look wrong</span>
              <span class="rig-card-sub">Asks the red question again.</span>
            </span>
            <span class="sd-channels" aria-hidden="true"><i class="r"></i><i class="g"></i><i class="b"></i></span>
            <Icon name="back" :size="18" class="sd-chev" />
          </span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* LightPane's own insides. Every rule here matches something this template draws, so `scoped`
   narrows it to the elements it already applied to, and these names can no longer collide with
   another screen's by accident.

   What stayed in panel.css, deliberately: anything on the component's outermost element, because
   that is where the rest of the sheet does its cross-cutting work and scoping would make a moved
   rule outrank the ones it used to tie with; any class another component also draws, which is
   shared vocabulary rather than ours; and any rule reaching in from a container (`.bento`,
   `.wall-stage`), which belongs to the arrangement rather than to this. */

.rig-auto-dot {
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  border-radius: 50%;
  /* the whole range a lamp on Automatic moves through in a day, which is what
     the word means here -- lamplight after dark, cooler while the sun is up */
  background: linear-gradient(135deg, #ffa657, #ffe9d4 52%, #e2ecff);
}
.rig-auto-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.rig-auto-name {
  font-size: 17px;
  font-weight: 500;
}
.rig-swatches {
  display: flex;
  flex-wrap: wrap;
  /* 11 with 46px swatches puts five to a 292 column, which is what turns fourteen swatches from four
     rows into three. */
  gap: 11px;
}
.rig-levels {
  flex: 1 1 0;
  /* 170, not 200: at 1440 the rig is 694 and the rest of it is 500, which holds the colors and the
     three at 170 with nothing to spare. At 200 they did not fit -- and, before the line was allowed
     to wrap, they did not fold either: the third column ran 18px off the side of the rig and the
     panel quietly clipped it. */
  min-width: 170px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  justify-content: center;
}
.rig-card {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 84px;
  padding: 0 22px;
  border-radius: 24px;
  border: 1px solid var(--edge);
  background: rgba(255, 255, 255, 0.05);
  color: var(--ink);
  text-align: left;
  font: inherit;
  cursor: pointer;
  transition: background 0.18s var(--ease);
}
.rig-card:hover {
  background: rgba(255, 255, 255, 0.09);
}
.rig-card.on {
  border-color: rgba(var(--lamp-rgb), 0.55);
  background: rgba(var(--lamp-rgb), 0.14);
}
.rig-card:disabled {
  opacity: 0.45;
  cursor: default;
}
.rig-card-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  color: var(--lamp);
  flex: 0 0 auto;
}
.rig-card-name {
  display: block;
  font-size: 19px;
}
.rig-card-sub {
  display: block;
  margin-top: 2px;
  font-size: 14px;
  color: var(--muted);
}
.rig-card.on .rig-card-sub {
  color: var(--ink-2);
}

/* WHERE THE STRIP'S ONE ROW SITS (design/strip/OneDoor.dc.html).

   The rig used to be one flat row that WRAPPED, which put the strip's rows across the whole width
   -- under the brightness column as well -- and left that column standing at half its height with
   nothing beneath it. Now everything that is not the brightness column is a column of its own, so
   the strip's row starts where the colors start and the brightness runs the full height it has on
   every other light's pane.

   The names here are this pane's own and are checked against panel.css before they are written:
   `rig-door` is a lock's, `rig-strip` is a sensor's, and either would have restyled a screen with
   nothing to do with a strip. AGENTS.md section 4. */
.rig-rest {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
  justify-content: center;
}
/* It wraps, because the rig is the width the pane leaves it and on a 1280 wall that is not enough
   for a brightness column, the colors and the three side by side. The three go under the colors
   then, and the strip's row stays under both -- which is the same arrangement, folded. Without this
   the row simply ran off the side of the screen. */
.rig-line {
  display: flex;
  flex-wrap: wrap;
  gap: 26px 26px;
  min-width: 0;
}
/* MORE COLORS FILLS THE RIG, as it did before the wrapper existed. Its two columns are dragged, so
   their height is the control -- a short hue column is a coarser one -- and inside a wrapper sized
   to its content they came out at a third of the pane. Only when that block is in: the line that
   holds the colors and the three keeps its own height, so the strip's row stays under them rather
   than being pushed to the floor. */
.rig-line:has(.rig-tune) {
  flex: 1 1 auto;
  min-height: 0;
}
.rig-ask {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
/* A sentence rather than two short words, so the card grows to its text instead of standing at the
   84px the three levels use and laying its second line across the card below. */
.rig-ask .rig-card {
  height: auto;
  min-height: 76px;
  padding: 16px 22px;
}
.rig-ask .rig-card-text {
  min-width: 0;
}
.rig-ask .rig-card-name em {
  font-style: normal;
  color: var(--muted);
}
.rig-ask .rig-card-sub {
  white-space: normal;
}
/* THE PICTURE DROPS TO ITS OWN LINE BEFORE THE WORDS GET SQUEEZED. On a 1440 wall the rig is 694
   wide and this row is 500 of it, which is not enough for a sentence AND a strip side by side --
   the name wrapped to three lines and the row stopped reading as a row. Flex-wrap rather than a
   container query: the strip is still drawn, across the whole card, which is if anything the better
   picture of a strip. */
.sd-door {
  gap: 16px 20px;
  flex-wrap: wrap;
}
.sd-door .rig-card-text {
  /* 200, not 260: a room with colors kept in it grows the block above by a label and a row of
     swatches, and on a 1440 wall that was the height the rig had left. At 260 this row took a second
     line for the picture and the foot of the rig went under the edge of the pane. */
  flex: 1 1 200px;
}
/* The panel has one chevron and it points back; a door that opens forward turns it round, the way
   three other rows in panel.css already do. `next` is the media icon -- a play triangle -- and it
   read as one. */
.sd-chev {
  flex: 0 0 auto;
  color: var(--muted);
  transform: rotate(180deg);
}

/* THE STRIP ITSELF, DRAWN. Sixty lights to the metre is what is under the shelf, so the marks are
   thin and close: the picture has to read as a strip at a glance and as an EDGE when looked at.
   The glow is on the lit part only -- a strip in a dark room is a line of light with a hard end,
   and the end is the whole subject. */
.sd-strip {
  position: relative;
  flex: 1 1 120px;
  max-width: 230px;
  height: 22px;
  border-radius: 4px;
  background: repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.13) 0 4px, transparent 4px 7px);
}
/* In the sheet the card is a column, so the picture must not be told to grow: it is 22px of strip
   across the whole card, not a panel. */
.sd-strip.wide {
  flex: 0 0 22px;
  max-width: none;
  display: block;
}
.sd-strip i {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  border-radius: 4px;
  background: repeating-linear-gradient(90deg, var(--lamp) 0 4px, transparent 4px 7px);
  filter: drop-shadow(0 0 8px rgba(var(--lamp-rgb), 0.65));
  transition: width 0.18s var(--ease);
}
/* the three channels, in the order the question is about: what red, green and blue come out as */
.sd-channels {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
  width: 130px;
}
/* one line, so the row reads as a row: the sentence under it is where the words go */
.sd-card .rig-card-name {
  white-space: nowrap;
}
.sd-channels i {
  flex: 1;
  height: 18px;
  border-radius: 4px;
}
.sd-channels .r {
  background: repeating-linear-gradient(90deg, #e2483e 0 4px, transparent 4px 7px), rgba(255, 255, 255, 0.03);
}
.sd-channels .g {
  background: repeating-linear-gradient(90deg, #4ac46a 0 4px, transparent 4px 7px), rgba(255, 255, 255, 0.03);
}
.sd-channels .b {
  background: repeating-linear-gradient(90deg, #4b86e8 0 4px, transparent 4px 7px), rgba(255, 255, 255, 0.03);
}

.sd-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  margin-bottom: 14px;
  padding: 20px 22px;
  border-radius: 24px;
  border: 1px solid var(--edge);
  background: rgba(255, 255, 255, 0.05);
  color: var(--ink);
  text-align: left;
  font: inherit;
}
.sd-card:last-child {
  margin-bottom: 0;
}
.sd-card.on {
  border-color: rgba(var(--lamp-rgb), 0.5);
  background: rgba(var(--lamp-rgb), 0.12);
}
.sd-card.on .rig-card-sub {
  color: var(--ink-2);
}
.sd-card-head {
  display: flex;
  align-items: center;
  gap: 16px;
}
.sd-tap {
  cursor: pointer;
}
.sd-tap:hover {
  background: rgba(255, 255, 255, 0.09);
}
.sd-tap:disabled {
  opacity: 0.45;
  cursor: default;
}
.sd-row {
  display: flex;
  gap: 12px;
}
.sd-row > * {
  flex: 1;
}
/* Big enough to hold, because holding is what this control is for, and the finger stays put while
   the strip moves under it. */
.sd-step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 56px;
  padding: 0 22px;
  border-radius: 999px;
  background: var(--surface-hi);
  border: 1px solid var(--edge);
  color: var(--ink);
  font: inherit;
  font-size: 16px;
  touch-action: none;
  user-select: none;
  cursor: pointer;
}
.sd-step:active {
  background: rgba(var(--lamp-rgb), 0.18);
  border-color: rgba(var(--lamp-rgb), 0.4);
}
.sd-step:disabled {
  opacity: 0.45;
}
/* The narrow panel's override, kept beside the rule it overrides. It used to live in panel.css's
   phone block, and once `.rig-levels` moved here the scoped rule outranked it by one attribute
   selector -- so at 860 and under the levels kept a 170px floor they were meant to drop. A class's
   whole cascade has to live in one place, media queries included. */
@media (max-width: 860px) {
  .rig-levels {
    min-width: 0;
  }
}
</style>
