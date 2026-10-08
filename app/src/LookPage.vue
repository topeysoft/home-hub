<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * How the house looks: one question, three answers.
 *
 * The house decides, not the screen. Pick one here and every panel in the place
 * changes at once, and a screen plugged in next year is already right — so this
 * saves to the hub rather than to the browser. That is also why there is no
 * "apply to this screen only": two screens in one house disagreeing about what
 * they look like is a bug, not a feature.
 *
 * What is NOT a disagreement is a phone laying the same look out as a column
 * while the wall lays it out as a row. That was three of the four questions this
 * page used to ask, and the screen has always known the answer better than the
 * person tapping — look.ts has the argument. So the page asks the one thing
 * nobody can answer for you, and says plainly underneath what it worked out on
 * its own, because a panel that quietly rearranges itself is worse than one that
 * asks.
 *
 * Nothing was taken away. Customize still holds all four, still writes them to
 * the house, and a house that set its look by hand before feels existed opens
 * this page already showing them. It is a disclosure, not a downgrade.
 *
 * Light or dark is the one exception, and the page says so first (design/appearance/,
 * B, decided 7 October). It is about the room a screen is in rather than about the
 * house -- a bright kitchen and a dark bedroom want different answers at the same
 * moment -- so it is kept on this screen and never sent to the hub (shade.ts).
 */
import { computed, ref } from 'vue'
import { setLook, type Look } from './api'
import { notify, store } from './store'
import { FACES, LAYOUTS, NAVS, isLayout, isNav } from './layout'
import { TONES, glassVars, toneVars, type ToneName } from './tone'
import { mix, palette, rgb, wxOf } from './sky'
import { FEELS, adjusted, feelFrom, lookOf, placeOf, TOUCHED_AT, type Feel, type FeelName } from './look'
import { defaultChoice, pick as pickShade, picked, shade, type ShadeChoice } from './shade'
import Icon from './Icon.vue'
import { isScreen, keepScreenRoom, screenRoom } from './screen'

const stored = computed<Partial<Look>>(() => store.ambient.look ?? {})
const feel = computed(() => feelFrom(stored.value))
const off = computed(() => adjusted(stored.value))
const busy = ref('')
const more = ref(off.value)      // a house that has already been in here opens on what it chose

/* what the four dials are actually set to, once the feel and the screen have
   had their say: the same resolution App.vue does, so the rows below can never
   disagree with the panel behind them */
const place = computed(() => placeOf(window.innerWidth))
const layout = computed(() => isLayout(stored.value.layout) ? stored.value.layout : 'auto')
const nav = computed(() => isNav(stored.value.nav) ? stored.value.nav : 'auto')
const tone = computed(() => stored.value.tone ?? feel.value.tone)
const face = computed(() => stored.value.face ?? feel.value.face)

/* A look shown as itself. Not a drawing of one and not a screenshot either: the
   sky is this hour's own three bands under the panel's own veil, the cards are
   the colors toneVars is handing the panel right now, and glass is the real
   material — the rules in panel.css reach .look-mini-card the same way they
   reach a room card. What you are looking at IS the answer, at the hour you are
   looking at it, which is the only honest way to ask someone to choose. */
function mini(f: Feel) {
  const { elevation, condition } = store.sky
  const [top, band, horizon] = palette(elevation, wxOf(condition), shade.value)
  return {
    ...toneVars(elevation, condition, f.tone, shade.value),
    ...(f.face === 'glass' ? glassVars(elevation, condition, f.tone, shade.value) : {}),
    '--mini-sky': `linear-gradient(180deg, ${rgb(top)}, ${rgb(band)} 56%, ${rgb(horizon)})`,
  }
}

async function write(look: Record<string, string>, key: string): Promise<boolean> {
  if (busy.value) return false
  busy.value = key
  const was = { ...stored.value }
  store.ambient.look = { ...was, ...look } as any      // the panel answers first; the hub confirms
  let ok = true
  try { store.ambient.look = await setLook(look as any) }
  catch (e: any) { store.ambient.look = was as any; notify(e.message, 'error'); ok = false }
  busy.value = ''
  return ok
}

/* Picking a feel is a reset as much as a choice: it writes the whole look, so
   the four dials go back to what this feel means and "adjusted" clears. That is
   also the only way back from Customize, which is why the reset below is the
   same call and not a fifth thing to maintain.
   
   And then it checks. A hub older than this panel keeps what it understands and
   drops the rest, so a pick can come back half-applied without anything failing:
   no error, no exception, just a page that quietly shows something other than
   what was tapped. feelFrom() means that is now rare rather than certain — face
   and tone are old enough to survive any hub — but "rare" is exactly the kind of
   thing that gets found by a person on a sofa rather than by a test, so if what
   came back is not what was asked for, say so instead of letting the tick slide
   back to Calm in silence. */
async function pick(id: FeelName) {
  if (busy.value || (feel.value.id === id && !off.value)) return
  const ok = await write(lookOf(id) as any, 'feel' + id)
  if (ok && feelFrom(store.ambient.look).id !== id) {
    notify('This hub is running an older version than the panel and could not keep that look. Update the hub and try again.', 'error')
  }
}

function choose(key: 'tone' | 'layout' | 'nav' | 'face', value: string) {
  const current = { tone: tone.value, layout: layout.value, nav: nav.value, face: face.value }[key]
  if (current === value) return
  return write({ [key]: value }, key + value)
}

/* Each swatch shows the tone as it is right now, under this sky: what you pick
   is what you are looking at, not a sample from some other hour.
   
   And on the face you are looking at it on. These were built from toneVars
   alone, which knows nothing about the face, so on glass they showed four
   different colors for four tones that all came out identical -- the swatch
   was the only part of the panel where the setting appeared to work. A pane is
   one material rather than three cards, so it gets one chip. */
function swatches(id: string) {
  const { elevation, condition } = store.sky
  if (face.value === 'glass') {
    /* A pane over the sky it will actually be over. On its own it is a chip of
       something 34% opaque laid on a dark row, which is very nearly nothing --
       honest, and unreadable. A pane has no color without a sky behind it;
       that is the whole of what the face is, and it is what .look-mini already
       does one section up. */
    const [top, band, horizon] = palette(elevation, wxOf(condition), shade.value)
    /* the BAND, not the whole ramp: a card sits on the middle of the sky rather
       than across all three of its bands, and squeezing the full ramp into 40px
       gave every chip the same strong top-to-bottom contrast to look at instead
       of the one thing that differs between them */
    const sky = `linear-gradient(180deg, ${rgb(mix(top, band, 0.72))}, ${rgb(mix(band, horizon, 0.35))})`
    const pane = glassVars(elevation, condition, id as ToneName, shade.value)['--glass']
    return [`${pane}, ${sky}`]
  }
  const v = toneVars(elevation, condition, id as ToneName, shade.value)
  return [v['--card-light'], v['--card-lock'], v['--card-plain']].filter(Boolean)
}

/* Light or dark, for this screen only. A phone gets a third answer, its own setting, which is
   also what it does until asked; a wall screen has no setting of its own to follow. */
const wide = window.innerWidth >= TOUCHED_AT
const shadeChoice = computed<ShadeChoice>(() => picked.value ?? defaultChoice(wide))
const SHADES: { id: ShadeChoice; label: string }[] = [
  ...(wide ? [] : [{ id: 'auto' as const, label: 'Same as phone' }]),
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
]

const AUTO_LAYOUT = computed(() => LAYOUTS.find(l => l.id === place.value.layout)!)
const AUTO_NAV = computed(() => NAVS.find(n => n.id === place.value.nav)!)
/* A wall screen's own room (design/companion/, C): Change asks again, the way it was asked the first time. */
const hangsIn = computed(() => isScreen() ? store.rooms.find(r => r.id === screenRoom())?.name ?? null : null)
const AROUND = computed(() => place.value.nav === 'top' ? 'with tabs across the top' : 'with the rooms alongside')
</script>

<template>
  <div class="page">
    <p class="page-lede">Everyone sees what you pick here, on every screen in the house. Light or dark is the one thing each screen picks for itself.</p>

    <h3 class="label">{{ wide ? 'This screen' : 'This phone' }}</h3>
    <div class="shade-opts" :class="{ two: wide }">
      <button v-for="s in SHADES" :key="s.id" class="shade-opt" :class="{ on: shadeChoice === s.id }" @click="pickShade(s.id)">
        <span class="shade-mini" aria-hidden="true">
          <span v-for="half in (s.id === 'auto' ? ['light', 'dark'] : [s.id])" :key="half" class="shade-mini-face" :data-mini-shade="half">
            <i></i><i class="lit"></i><i class="wide"></i>
          </span>
        </span>
        <span class="shade-name">{{ s.label }}<span class="look-tick" v-if="shadeChoice === s.id"><Icon name="check" :size="11" /></span></span>
      </button>
    </div>
    <p class="shade-hint">{{ wide ? 'Only this screen. Phones pick their own.' : 'Only this phone. The wall screen is set on the wall screen.' }}</p>
    <p class="shade-hint" v-if="hangsIn">This screen is in <b>{{ hangsIn }}</b>. <button class="linkish" @click="keepScreenRoom(null)">Change</button></p>

    <div class="look-feels">
      <button v-for="f in FEELS" :key="f.id" class="look-feel"
              :class="{ on: feel.id === f.id, busy: busy === 'feel' + f.id }" @click="pick(f.id)">
        <span class="look-mini" :data-face="f.face" :style="mini(f)" aria-hidden="true">
          <i class="look-mini-sky"></i>
          <i class="look-mini-bloom" v-if="f.face === 'glass'"></i>
          <i class="look-mini-veil"></i>
          <span class="look-mini-panel">
            <i class="look-mini-card head"></i>
            <i class="look-mini-card lit"></i>
            <i class="look-mini-card lock"></i>
            <i class="look-mini-card plain"></i>
            <i class="look-mini-card wide"></i>
          </span>
        </span>
        <span class="look-feel-name">
          {{ f.label }}<span class="look-tick" v-if="feel.id === f.id"><Icon name="check" :size="11" /></span>
        </span>
        <span class="look-hint">{{ f.hint }}</span>
      </button>
    </div>

    <p class="look-place">
      <span v-if="off">Showing <b>{{ feel.label }}, adjusted</b> — some of it was set by hand below.</span>
      <span v-else>This screen is laid out as a <b>{{ AUTO_LAYOUT.label.toLowerCase() }}</b>, {{ AROUND }}. A phone in the same house shows the same look, laid out for a phone.</span>
    </p>
    <button v-if="off" class="look-reset" :class="{ busy: busy === 'feel' + feel.id }" @click="pick(feel.id)">
      <Icon name="refresh" :size="14" /> Back to {{ feel.label }}
    </button>

    <button class="look-more" :class="{ open: more }" @click="more = !more">
      <span>Customize this look</span>
      <Icon name="back" :size="15" />
    </button>

    <div v-if="more" class="look-custom">
      <h3 class="label">Home</h3>
      <div class="look-rows">
        <button class="look-row" :class="{ on: layout === 'auto', busy: busy === 'layoutauto' }" @click="choose('layout', 'auto')">
          <span class="look-text">
            <span class="look-name">Automatic<span class="look-tick" v-if="layout === 'auto'"><Icon name="check" :size="11" /></span></span>
            <span class="look-hint">Each screen arranges itself. This one: {{ AUTO_LAYOUT.label.toLowerCase() }}.</span>
          </span>
          <span class="look-shape" :class="'look-' + AUTO_LAYOUT.id" aria-hidden="true"><i></i><i></i><i></i></span>
        </button>
        <button v-for="l in LAYOUTS" :key="l.id" class="look-row" :class="{ on: layout === l.id, busy: busy === 'layout' + l.id }" @click="choose('layout', l.id)">
          <span class="look-text">
            <span class="look-name">{{ l.label }}<span class="look-tick" v-if="layout === l.id"><Icon name="check" :size="11" /></span></span>
            <span class="look-hint">{{ l.hint }}</span>
          </span>
          <!-- prefixed: a bare "rail" here would also match the navigation rail's own class -->
          <span class="look-shape" :class="'look-' + l.id" aria-hidden="true"><i></i><i></i><i></i></span>
        </button>
      </div>

      <h3 class="label">Getting around</h3>
      <div class="look-rows">
        <button class="look-row" :class="{ on: nav === 'auto', busy: busy === 'navauto' }" @click="choose('nav', 'auto')">
          <span class="look-text">
            <span class="look-name">Automatic<span class="look-tick" v-if="nav === 'auto'"><Icon name="check" :size="11" /></span></span>
            <span class="look-hint">Each screen decides. This one: {{ AUTO_NAV.label.toLowerCase() }}.</span>
          </span>
          <span class="look-shape" :class="'look-nav-' + AUTO_NAV.id" aria-hidden="true"><i></i><i></i></span>
        </button>
        <button v-for="n in NAVS" :key="n.id" class="look-row" :class="{ on: nav === n.id, busy: busy === 'nav' + n.id }" @click="choose('nav', n.id)">
          <span class="look-text">
            <span class="look-name">{{ n.label }}<span class="look-tick" v-if="nav === n.id"><Icon name="check" :size="11" /></span></span>
            <span class="look-hint">{{ n.hint }}</span>
          </span>
          <span class="look-shape" :class="'look-nav-' + n.id" aria-hidden="true"><i></i><i></i></span>
        </button>
      </div>

      <h3 class="label">What it is made of</h3>
      <div class="look-rows">
        <button v-for="fc in FACES" :key="fc.id" class="look-row" :class="{ on: face === fc.id, busy: busy === 'face' + fc.id }" @click="choose('face', fc.id)">
          <span class="look-text">
            <span class="look-name">{{ fc.label }}<span class="look-tick" v-if="face === fc.id"><Icon name="check" :size="11" /></span></span>
            <span class="look-hint">{{ fc.hint }}</span>
          </span>
          <span class="look-shape" :class="'look-face-' + fc.id" aria-hidden="true"><i></i><i></i></span>
        </button>
      </div>

      <h3 class="label">Cards</h3>
      <div class="look-rows">
        <button v-for="t in TONES" :key="t.id" class="look-row" :class="{ on: tone === t.id, busy: busy === 'tone' + t.id }" @click="choose('tone', t.id)">
          <span class="look-text">
            <span class="look-name">{{ t.label }}<span class="look-tick" v-if="tone === t.id"><Icon name="check" :size="11" /></span></span>
            <span class="look-hint">{{ t.hint }}</span>
          </span>
          <span class="look-swatch" :class="{ one: face === 'glass' }" aria-hidden="true"><i v-for="(s, i) in swatches(t.id)" :key="i" :style="{ background: s }"></i></span>
        </button>
      </div>

      <p class="page-foot">The cards take their color from the sky, so all of these lighten through the morning and settle after sunset. The tone sets which way they lean.</p>
    </div>
  </div>
</template>

<style scoped>
/* Light or dark, drawn as itself. The two little pages are pictures of a shade, not this screen's
   shade, so their colors are fixed: a light one is light even while you look at it on a dark screen. */
.shade-opts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.shade-opts.two {
  grid-template-columns: repeat(2, minmax(0, 200px));
}
.shade-opt {
  display: grid;
  gap: 8px;
  align-content: start;
  padding: 10px 10px 12px;
  border-radius: 20px;
  background: var(--surface-hi);
  border: 1px solid var(--edge);
  transition: background 0.18s var(--ease), border-color 0.18s var(--ease);
}
.shade-opt:active {
  transform: scale(0.99);
}
.shade-opt.on {
  background: linear-gradient(rgba(var(--lamp-rgb), 0.12), rgba(var(--lamp-rgb), 0.12)), var(--surface);
  border-color: rgba(var(--lamp-rgb), 0.55);
}
.shade-mini {
  position: relative;
  display: block;
  aspect-ratio: 4 / 3;
  border-radius: var(--r-sm);
  overflow: hidden;
}
.shade-mini-face {
  position: absolute;
  inset: 0;
}
.shade-mini-face + .shade-mini-face {
  clip-path: polygon(100% 0, 100% 100%, 0 100%);
}
.shade-mini-face[data-mini-shade='light'] {
  background: linear-gradient(180deg, oklch(0.8 0.06 245), oklch(0.89 0.04 230) 60%, oklch(0.94 0.02 95));
}
.shade-mini-face[data-mini-shade='dark'] {
  background: linear-gradient(180deg, rgb(10, 14, 34), rgb(38, 34, 74) 60%, rgb(110, 66, 66));
}
.shade-mini-face i {
  position: absolute;
  left: 10%;
  top: 12%;
  width: 37%;
  height: 36%;
  border-radius: 5px;
}
.shade-mini-face i.wide {
  top: 54%;
  width: 80%;
}
.shade-mini-face[data-mini-shade='light'] i {
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 2px 6px -2px oklch(0.36 0.05 245 / 0.35);
}
.shade-mini-face[data-mini-shade='dark'] i {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
}
.shade-mini-face i.lit {
  left: 53%;
  background: linear-gradient(160deg, oklch(0.9 0.095 82), oklch(0.82 0.12 70));
  border: 0;
}
.shade-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15.5px;
  font-weight: 500;
}
.shade-hint {
  margin: 10px 0 20px;
  font-size: 13.5px;
  color: var(--ink-2);
}
</style>
