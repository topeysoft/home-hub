<script setup lang="ts">
/*
 * Outside, opened in place.
 *
 * The pane every card already opens, on a thing that is not a device. The whole
 * argument for it is in one absence: THERE IS NO ROW OF VERBS HERE. Every other
 * pane has one under the name, and the weather has nothing to do — so this is a
 * reading held open, not a control surface.
 *
 * That matters because WallView.vue is explicit that the weather is not in the
 * house: it is scenery, it travels at its own rate, it is deliberately not a
 * card. A tap that opened a control would be the lozenge pretending to be one of
 * the things the house owns. A tap that opens a page of numbers is the sky
 * saying more about itself, and nothing changes underneath it — which is also
 * what keeps the rule that nothing vanishes under a tap.
 *
 * And it is what buys the lozenge back. Everything that wanted a fifth line in a
 * 226px pane — the forecast, the day, inside against outside — is here instead,
 * at a size that is read at arm's length because somebody walked over and
 * touched it. The lozenge stays a glance.
 *
 * Nothing about the chrome is new: .opened, its veil, its four beats and
 * .pane-rig are the same ones Opened.vue uses, which is why this file is short.
 * See design/weather for the board.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, weatherParts, WEATHER_LABEL } from './store'
import { nextSun } from './upcoming'
import { ahead, changeLine, days, inside, listed, nextChange, openThings, range, WET } from './weather'
import Icon from './Icon.vue'
import WeatherArt from './WeatherArt.vue'

/* the panel's clock rather than this pane's own: ?at= previews an hour and a
   pane that ignored it would put the forecast in a different afternoon from the
   screen behind it */
const props = defineProps<{ now: Date }>()
const now = computed(() => props.now)

const temp = computed(() => weatherParts().temp)
const says = computed(() => weatherParts().label || 'Outside')
const unit = computed(() => (store.ambient.weather?.unit || '°').replace(/[^°]/g, '') || '°')
const deg = (v: number | null | undefined) => v == null ? '—' : `${Math.round(v)}${unit.value}`

/* The one paragraph, and it is built rather than written: what is coming, then
   the house's own stake in it where there is one. When nothing is coming the
   day's range takes the sentence instead, because a pane that opens onto an
   empty line is worse than one that opens onto a fact. */
const why = computed(() => {
  const parts: string[] = []
  const change = changeLine(now.value, undefined, undefined)
  const r = range(now.value)
  if (change) parts.push(change + '.')
  else if (r) parts.push(`High ${deg(r.high)}, low ${deg(r.low)} today.`)
  /* only where the weather is actually the house's business: rain coming, and something open to
     close. On a clear afternoon an open window is not news and this stays quiet. */
  const coming = nextChange(now.value)
  const open = openThings()
  if (coming?.kind === 'starts' && open.length) parts.push(`${listed(open)} ${open.length === 1 ? 'is' : 'are'} open.`)
  return parts.join(' ')
})

const facts = computed(() => {
  const w = store.ambient.weather
  const out: { k: string; v: string }[] = []
  if (w?.humidity != null) out.push({ k: 'Humidity', v: `${Math.round(w.humidity)}%` })
  if (w?.wind_speed != null) out.push({ k: 'Wind', v: `${Math.round(w.wind_speed)} ${w.wind_unit ?? ''}`.trim() })
  const up = store.sky.elevation > -0.833
  const at = nextSun(now.value, !up)
  if (at) out.push({ k: up ? 'Sunset' : 'Sunrise', v: at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) })
  const warm = inside()
  if (warm != null) out.push({ k: 'Inside', v: deg(warm) })
  return out
})

/* The hours, as a row of marks. The bar's height is the reading's place between
   the coldest and the warmest hour on show rather than an absolute scale: a day
   that moves four degrees should still read as a shape, and one that moves
   thirty must not run off the top. */
const hours = computed(() => {
  const rows = ahead(now.value).slice(0, 8)
  const reads = rows.map(h => h.temperature).filter((t): t is number => t != null)
  const lo = Math.min(...reads), hi = Math.max(...reads)
  return rows.map((h, i) => ({
    key: h.at,
    when: i === 0 ? 'Now' : new Date(h.at).toLocaleTimeString([], { hour: 'numeric' }),
    temp: h.temperature == null ? '' : deg(h.temperature),
    wet: WET.has(h.condition),
    /* 12px of bar even where every hour is the same reading, so a flat day is a row and not a gap */
    height: reads.length < 2 || hi === lo ? 30 : 12 + Math.round(((h.temperature ?? lo) - lo) / (hi - lo) * 44),
  }))
})

/* The days. The bar under each is where that day's range sits inside the whole
   week's, which is the comparison somebody actually makes: is tomorrow warmer. */
const week = computed(() => {
  const rows = days(now.value).slice(0, 5)
  const all = rows.flatMap(d => [d.high, d.low]).filter((t): t is number => t != null)
  const lo = Math.min(...all), hi = Math.max(...all)
  const place = (v: number | null) => v == null || hi === lo ? 50 : ((v - lo) / (hi - lo)) * 100
  return rows.map((d, i) => ({
    key: d.at,
    name: i === 0 ? 'Today' : new Date(d.at).toLocaleDateString([], { weekday: 'long' }),
    wet: WET.has(d.condition),
    says: WEATHER_LABEL[d.condition] ?? '',
    low: deg(d.low), high: deg(d.high),
    from: place(d.low), to: place(d.high),
  }))
})

/* Whether there is a forecast to draw at all. Plenty of weather integrations
   serve none, and the hub passes through whatever it got -- so this is a real
   house, not an edge case, and what fills the other half of the pane when it is
   false is as much a part of the design as the forecast is. */
const anything = computed(() => hours.value.length > 0 || week.value.length > 0)

/* the same two frames and the same 320ms Opened.vue counts; panel.css says why */
const shown = ref(false), closing = ref(false)
function close() { shown.value = false; closing.value = true; setTimeout(() => (store.outside = false), 320) }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="opened outside" :class="{ shown, closing }" role="dialog" aria-label="Outside">
    <div class="opened-veil" @click="close"></div>
    <div class="opened-panel">
      <button class="back opened-close" @click="close" aria-label="Close"><Icon name="close" :size="18" /></button>

      <div class="opened-body pane-body">
        <div class="pane-said">
          <div class="opened-step s0">
            <div class="opened-room">Outside</div>
            <h2 class="display opened-name">{{ says }}</h2>
          </div>

          <!-- Slot two, the row of verbs, is deliberately empty: there is nothing
               to do to the weather. The file header says why that is the point. -->

          <div class="opened-step s2">
            <div class="opened-big display" v-if="temp">{{ temp }}</div>
            <p class="pane-why" v-if="why">{{ why }}</p>
          </div>
        </div>

        <div class="opened-step s3 opened-facts pane-facts" v-if="facts.length">
          <div v-for="f in facts" :key="f.k">
            <div class="opened-fact-v">{{ f.v }}</div>
            <div class="opened-fact-k">{{ f.k }}</div>
          </div>
        </div>

        <!-- the instrument: what a 226px lozenge is too small for -->
        <div class="pane-rig wx-rig" :class="{ art: !anything }">
          <!-- and when the house has no forecast, the sky's own drawing at a size
               the wall never gives it. The alternative was leaving this half of
               the pane empty, which at a wall's width is most of the screen: a
               pane that opens onto nothing is worse than the lozenge it came
               from. This is the one thing here that is always worth drawing,
               because it is what the pane is ABOUT. -->
          <WeatherArt class="wx-art" v-if="!anything" />
          <div class="wx-ahead" v-else>
            <div class="wx-hours" v-if="hours.length">
              <div class="wx-hour" v-for="h in hours" :key="h.key">
                <div class="wx-hour-t">{{ h.temp }}</div>
                <div class="wx-hour-bar" :class="{ wet: h.wet }" :style="{ height: h.height + 'px' }"></div>
                <div class="wx-hour-k">{{ h.when }}</div>
              </div>
            </div>

            <div class="wx-rule" v-if="hours.length && week.length"></div>

            <div class="wx-days" v-if="week.length">
              <div class="wx-day" v-for="d in week" :key="d.key">
                <div class="wx-day-n">{{ d.name }}<span class="wx-day-s" v-if="d.wet">{{ d.says }}</span></div>
                <div class="wx-day-lo">{{ d.low }}</div>
                <div class="wx-day-bar"><i :style="{ left: d.from + '%', right: (100 - d.to) + '%' }"></i></div>
                <div class="wx-day-hi">{{ d.high }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
