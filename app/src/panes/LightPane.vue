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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import type { Device } from '../api'
import { keepColor, listStrips, revisitStrip, type StripRow } from '../api'
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
  const n = strip.value?.count
  return n ? `About ${(n / 60).toFixed(1)} m` : 'Measured once'
})
const asking = ref(false)
async function askAgain(what: 'colors' | 'length') {
  if (!strip.value || asking.value) return
  asking.value = true
  try { store.strip = await revisitStrip(strip.value.id, what) }
  catch (e: any) { notify(e.message, 'error') }
  asking.value = false
}

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
      <template v-if="kept.length">
        <span class="rig-lbl">This room</span>
        <div class="rig-swatches">
          <button v-for="c in kept" :key="`k${c.hue}-${c.amount}`" class="rig-swatch" :class="{ on: chosen({ kind: 'color', ...c }) }"
                  :style="{ background: swatch({ kind: 'color', ...c }) }" :disabled="dead"
                  :aria-label="`Kept color, hue ${c.hue}`" :aria-pressed="chosen({ kind: 'color', ...c })"
                  @click="choose({ kind: 'color', ...c })"></button>
        </div>
        <span class="rig-lbl">Color</span>
      </template>
      <div class="rig-swatches" v-if="canColor">
        <button v-for="c in COLORS" :key="c.hue" class="rig-swatch" :class="{ on: chosen({ kind: 'color', ...c }) }"
                :style="{ background: swatch({ kind: 'color', ...c }) }" :disabled="dead"
                :aria-label="`Color, hue ${c.hue}`" :aria-pressed="chosen({ kind: 'color', ...c })"
                @click="choose({ kind: 'color', ...c })"></button>
      </div>
      <template v-if="canWhite">
        <span class="rig-lbl">White</span>
        <div class="rig-swatches">
          <button v-for="k in WHITES" :key="k" class="rig-swatch" :class="{ on: chosen({ kind: 'white', kelvin: k }) }"
                  :style="{ background: swatch({ kind: 'white', kelvin: k }) }" :disabled="dead"
                  :aria-label="`White, ${k} kelvin`" :aria-pressed="chosen({ kind: 'white', kelvin: k })"
                  @click="choose({ kind: 'white', kelvin: k })"></button>
        </div>
      </template>
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

    <!-- The strip-shaped part, and the only part of this pane that knows what a strip is. AT THE
         FOOT and across the whole width, not a column beside the others: the board's argument is
         that a strip is an ordinary light with two extra rows, and a fourth column squeezes the
         three things this pane is actually for. -->
    <div class="rig-ask" v-if="strip && !tuning">
      <span class="rig-lbl">Because it is a strip</span>
      <button class="rig-card" :disabled="dead || asking || !strip.online" @click="askAgain('length')">
        <span class="rig-card-icon"><Icon name="pin" :size="18" /></span>
        <span class="rig-card-text">
          <span class="rig-card-name">Ends here <em>{{ metres }}</em></span>
          <span class="rig-card-sub">Say again if you cut it down, or joined another on.</span>
        </span>
      </button>
      <button class="rig-card" :disabled="dead || asking || !strip.online" @click="askAgain('colors')">
        <span class="rig-card-icon"><Icon name="light" :size="18" /></span>
        <span class="rig-card-text">
          <span class="rig-card-name">The colors look wrong</span>
          <span class="rig-card-sub">Asks the red question again. A strip bought later may not be the same make.</span>
        </span>
      </button>
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
  gap: 13px;
}
.rig-levels {
  flex: 1 1 0;
  min-width: 200px;
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

/* THE TWO ROWS A STRIP ADDS, at the foot and across the whole width.
   The wrap is switched on only when there IS a strip, so no other light's pane can be moved by a
   rule it has no element for. And the card here grows to its text rather than standing at the
   84px the three levels use: those are two short words and these are a sentence, and a fixed
   height with a sentence in it is text lying across the card below -- which is what it did. */
.rig-has-strip {
  flex-wrap: wrap;
}
.rig-ask {
  flex: 1 0 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
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
}</style>
