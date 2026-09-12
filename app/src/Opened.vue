<script setup lang="ts">
/*
 * One device, opened in place.
 *
 * The home does not get covered, it recedes: scaled back, blurred and dimmed,
 * so the panel reads as something in front of the house rather than a new page.
 * The timings are measured, not invented — 320ms for the home to fall back,
 * 380ms for the panel to rise, and the hero arrives 80ms late and travels
 * further than the panel does, which is what makes it feel like an object
 * instead of a picture. Content comes up behind it in four beats.
 *
 * Those are paper's. Glass has a measured set of its own, and a room that dims
 * rather than blurring — all of it in panel.css under [data-face='glass'], none
 * of it here, because a face gets to change how a thing moves and not what it
 * is. The one exception is `closing` below, which exists because CSS cannot see
 * the difference between a pane that has not risen yet and one on its way out.
 *
 * The field takes the device's own colour while it is open: a warm lamp pushes
 * the whole room amber, a camera cools it. That is the one idea worth stealing
 * from the reference this was drawn from, and the sky gives it somewhere real
 * to sit. Everything here sits behind the app's reduced-motion block, which
 * turns the whole sequence into a plain cross-fade.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { act } from './api'
import { cap, isDead, notify, perform, roomOf, store } from './store'
import Icon from './Icon.vue'

const dev = computed(() => store.opened)
const kind = computed(() => dev.value ? cap(dev.value) : '')
const room = computed(() => dev.value ? roomOf(dev.value)?.name ?? '' : '')
const shown = ref(false)              // flipped a frame after mount, so the transitions have a from-state to leave from

/* the one number worth saying in large type: how bright, how warm, or just what it is doing */
const big = computed(() => {
  const d = dev.value; if (!d) return ''
  const a = d.attrs ?? {}
  if (dead.value) return 'Not answering'
  if (kind.value === 'light' && d.state === 'on' && a.brightness != null) return Math.round((a.brightness / 255) * 100) + '%'
  if (kind.value === 'climate' && a.current_temperature != null) return Math.round(a.current_temperature) + '°'
  if (kind.value === 'cover' && a.current_position != null) return a.current_position + '%'
  if (kind.value === 'fan' && d.state === 'on' && a.percentage) return a.percentage + '%'
  return d.state === 'on' ? 'On' : d.state === 'playing' ? 'Playing' : d.state === 'off' ? 'Off' : d.state
})
/* only what this particular device actually knows about itself: no filler rows */
const facts = computed(() => {
  const d = dev.value; if (!d) return [] as { k: string; v: string }[]
  const a = d.attrs ?? {}
  const out: { k: string; v: string }[] = []
  if (a.color_temp_kelvin) out.push({ k: 'Warmth', v: a.color_temp_kelvin + 'K' })
  if (kind.value === 'climate' && a.temperature != null) out.push({ k: 'Set to', v: Math.round(a.temperature) + '°' })
  if (a.media_title) out.push({ k: 'Playing', v: String(a.media_title) })
  if (a.percentage != null && kind.value === 'fan') out.push({ k: 'Speed', v: a.percentage + '%' })
  if (d.maker) out.push({ k: 'Made by', v: d.maker })   // hw is the registry's opaque id, never worth showing
  return out.slice(0, 3)
})

const dead = computed(() => !!dev.value && isDead(dev.value))
const on = computed(() => dev.value?.state === 'on' || dev.value?.state === 'playing')
async function toggle() {
  const d = dev.value; if (!d || dead.value) return
  try { await act(d.id, on.value ? 'off' : 'on') } catch (e: any) { notify(e.message, 'error') }
}
/* the panel has to be worth opening: the tile can already toggle, so what it
   owes is the control the tile is too small for. For a light that is the dimmer,
   at a size you can hit without looking. */
const dimmable = computed(() => kind.value === 'light' && !!dev.value && 'brightness' in (dev.value.attrs ?? {}))
const pct = computed(() => {
  const b = dev.value?.attrs?.brightness
  return dev.value?.state === 'on' && b != null ? Math.round((b / 255) * 100) : 0
})
async function dim(e: Event) {
  const d = dev.value; if (!d) return
  const v = Number((e.target as HTMLInputElement).value)
  try { await perform(d, 'on', { brightness_pct: v }, { state: 'on', attrs: { brightness: Math.round(v * 2.55) } }) }
  catch (err: any) { notify(err.message, 'error') }
}

/* `closing` is not the same fact as `!shown`, and the difference is two frames:
   between mounting and the rise beginning, the pane is also not shown, and CSS
   cannot tell those two apart. Something has to, because the bottom bar's way
   back is counted from the moment the fall STARTS -- see panel.css. The
   timeout is a frame past the longest fall either face has, paper's 280ms and
   glass's 300, so the last of the slide is never clipped. */
const closing = ref(false)
function close() { shown.value = false; closing.value = true; setTimeout(() => (store.opened = null), 320) }

function onKey(e: KeyboardEvent) { if (e.key === 'Escape') close() }
/* Two frames, not one. onMounted runs before the browser has painted anything,
   and a single requestAnimationFrame still lands inside the frame that paints
   the panel for the first time -- so `shown` was already on by that first paint
   and there was nothing to transition from: the panel simply appeared. The
   second frame is the one that gets painted down at translateY(100%), and the
   rise begins from there. Closing never had the problem, which is why it was
   only ever wrong in one direction. */
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="opened" :class="{ shown, closing }" v-if="dev" role="dialog" :aria-label="dev.name">
    <div class="opened-veil" @click="close"></div>
    <div class="opened-panel" :data-cap="kind">
      <button class="back opened-close" @click="close" aria-label="Close"><Icon name="close" :size="18" /></button>

      <!-- the hero: late, and travelling further than the panel did -->
      <span class="opened-hero" aria-hidden="true"><Icon :name="kind || 'switch'" :size="260" /></span>

      <div class="opened-body">
        <div class="opened-step s0">
          <div class="opened-room" v-if="room">{{ room }}</div>
          <h2 class="display opened-name">{{ dev.name }}</h2>
        </div>

        <div class="opened-step s1 opened-acts">
          <button class="ctl primary" :class="{ off: !on }" @click="toggle" :disabled="dead" :aria-label="on ? 'Turn off' : 'Turn on'">
            <Icon name="power" :size="22" />
          </button>
          <button class="ctl" v-if="kind === 'camera'" @click="store.viewer = dev; close()" aria-label="Watch"><Icon name="camera" :size="20" /></button>
          <button class="ctl" @click="store.sheet = 'why'" aria-label="Why did this happen"><Icon name="sparkle" :size="20" /></button>
        </div>

        <div class="opened-step s2 opened-big display">{{ big }}</div>

        <div class="opened-step s3 opened-dim" v-if="dimmable" :style="{ '--dim': pct + '%' }">
          <input type="range" min="1" max="100" :value="pct" :disabled="dead" @change="dim" @input="dim" aria-label="Brightness" />
          <p class="opened-dim-hint">Drag to dim. It stays here until a routine moves it.</p>
        </div>

        <div class="opened-step s3 opened-facts" v-if="facts.length">
          <div v-for="f in facts" :key="f.k">
            <div class="opened-fact-v">{{ f.v }}</div>
            <div class="opened-fact-k">{{ f.k }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
