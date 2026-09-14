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
 * Nothing was taken away. Customise still holds all four, still writes them to
 * the house, and a house that set its look by hand before feels existed opens
 * this page already showing them. It is a disclosure, not a downgrade.
 */
import { computed, ref } from 'vue'
import { setLook, type Look } from './api'
import { notify, store } from './store'
import { FACES, LAYOUTS, NAVS, isLayout, isNav } from './layout'
import { TONES, glassVars, toneVars } from './tone'
import { palette, rgb, wxOf } from './sky'
import { FEELS, adjusted, feelFrom, lookOf, placeOf, type Feel, type FeelName } from './look'
import Icon from './Icon.vue'

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
   the colours toneVars is handing the panel right now, and glass is the real
   material — the rules in panel.css reach .look-mini-card the same way they
   reach a room card. What you are looking at IS the answer, at the hour you are
   looking at it, which is the only honest way to ask someone to choose. */
function mini(f: Feel) {
  const { elevation, condition } = store.sky
  const [top, band, horizon] = palette(elevation, wxOf(condition))
  return {
    ...toneVars(elevation, condition, f.tone),
    ...(f.face === 'glass' ? glassVars(elevation, condition) : {}),
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
   also the only way back from Customise, which is why the reset below is the
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

/* each swatch shows the tone as it is right now, under this sky: what you pick
   is what you are looking at, not a sample from some other hour */
function swatches(id: string) {
  const v = toneVars(store.sky.elevation, store.sky.condition, id as any)
  return [v['--card-light'], v['--card-lock'], v['--card-plain']].filter(Boolean)
}

const AUTO_LAYOUT = computed(() => LAYOUTS.find(l => l.id === place.value.layout)!)
const AUTO_NAV = computed(() => NAVS.find(n => n.id === place.value.nav)!)
const AROUND = computed(() => place.value.nav === 'top' ? 'with tabs across the top' : 'with the rooms alongside')
</script>

<template>
  <div class="page">
    <p class="page-lede">Everyone sees what you pick here, on every screen in the house.</p>

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
      <span>Customise this look</span>
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
          <span class="look-swatch" aria-hidden="true"><i v-for="(s, i) in swatches(t.id)" :key="i" :style="{ background: s }"></i></span>
        </button>
      </div>

      <p class="page-foot">The cards take their colour from the sky, so all of these lighten through the morning and settle after sunset. The tone sets which way they lean.</p>
    </div>
  </div>
</template>
