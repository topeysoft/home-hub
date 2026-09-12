<script setup lang="ts">
/*
 * How the house looks: an arrangement for Home and a tone for the cards.
 *
 * The house decides, not the screen. Pick one here and every panel in the place
 * changes at once, and a screen plugged in next year is already right — so this
 * saves to the hub rather than to the browser. That is also why there is no
 * "apply to this screen only": two screens in one house disagreeing about what
 * they look like is a bug, not a feature.
 */
import { computed, ref } from 'vue'
import { setLook } from './api'
import { notify, store } from './store'
import { FACES, LAYOUTS, NAVS } from './layout'
import { TONES, toneVars } from './tone'
import Icon from './Icon.vue'

const layout = computed(() => store.ambient.look?.layout ?? 'stack')
const tone = computed(() => store.ambient.look?.tone ?? 'follow')
const nav = computed(() => store.ambient.look?.nav ?? 'side')
const face = computed(() => store.ambient.look?.face ?? 'paper')
const busy = ref('')

/* each swatch shows the tone as it is right now, under this sky: what you pick
   is what you are looking at, not a sample from some other hour */
function swatches(id: string) {
  const v = toneVars(store.sky.elevation, store.sky.condition, id as any)
  return [v['--card-light'], v['--card-lock'], v['--card-plain']].filter(Boolean)
}

async function choose(key: 'tone' | 'layout' | 'nav' | 'face', value: string) {
  const current = { tone: tone.value, layout: layout.value, nav: nav.value, face: face.value }[key]
  if (busy.value || current === value) return
  busy.value = key + value
  const was = { ...(store.ambient.look ?? {}) }
  store.ambient.look = { tone: tone.value, layout: layout.value, nav: nav.value, face: face.value, [key]: value }   // the panel answers first; the hub confirms
  try { store.ambient.look = await setLook({ [key]: value }) }
  catch (e: any) { store.ambient.look = was as any; notify(e.message, 'error') }
  busy.value = ''
}
</script>

<template>
  <div class="page">
    <p class="page-lede">Everyone sees what you pick here, on every screen in the house.</p>

    <h3 class="label">Home</h3>
    <div class="look-rows">
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
</template>
