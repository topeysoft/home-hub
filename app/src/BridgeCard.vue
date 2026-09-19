<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { setBridgeLight, forgetBridge, type BridgeRow } from './api'
import { notify } from './store'
import Icon from './Icon.vue'

/*
 * One bridge, looked at on purpose.
 *
 * Until this existed a puck surfaced on the panel only when something was WRONG with it -- a note
 * when it went quiet, a line on This hub when it was a version behind -- so the only place a
 * household could act on one was a problem report. That is the wrong shape for an object that
 * mostly just works, and it is what left the nightlight's "lift on motion" reachable nowhere but
 * Home Assistant, which product-direction-out-of-the-box forbids. docs/puck-light.md, step 5.
 *
 * Three brightnesses rather than a slider, because this panel has no sliders: brightness everywhere
 * else in the house is a gesture on the thing itself, and the nightlight IS a light in the house --
 * so anybody who wants a level between these has its own tile to do it on. What belongs here is the
 * handful of decisions that are about the BRIDGE, and they are all named in words.
 */
const props = defineProps<{ bridge: BridgeRow }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'changed', rows: BridgeRow[]): void }>()

const b = computed(() => props.bridge)
const busy = ref('')
/* A puck the hub has never heard speak cannot have its light drawn in either position. Saying so is
   the honest thing; a switch showing "off" for a thing that has not answered is a small lie that
   costs somebody an evening. */
const heard = computed(() => b.value.night !== null && b.value.night !== undefined)

const LEVELS = [{ id: 'dim', label: 'Dim', to: 60 }, { id: 'soft', label: 'Soft', to: 110 }, { id: 'bright', label: 'Bright', to: 200 }]
const nearest = computed(() => {
  const n = b.value.level ?? 110
  return LEVELS.reduce((best, l) => Math.abs(l.to - n) < Math.abs(best.to - n) ? l : best, LEVELS[1]).id
})

/* SAY ONLY WHAT THE HOUSE ACTUALLY KNOWS -- pane.ts's rule, and this line broke it twice.
 *
 * `signal: 'none'` is not a weak signal, it is NO ANSWER: the brain returns it for a puck that is
 * offline AND for one that is on the broker but has not said which node it is linked to, which is
 * every puck in the seconds after it connects and any puck that cannot find a switch at all. Falling
 * through to the last branch made that read "Strong", which is a claim the hub cannot make about a
 * link it has never seen. And "hears 0 switches" was arithmetic where a sentence was wanted. */
const state = computed(() => {
  const { online, signal, switches } = b.value
  if (!online) return 'Not answering. It may be unplugged, or out of Wi‑Fi reach.'
  // Nothing to bridge is the more useful thing to say than how loud the link to nothing is.
  if (!switches) return 'It has not heard a switch yet. A socket nearer one would give it something to bridge.'
  const hears = switches === 1 ? 'hears 1 switch' : `hears ${switches} switches`
  if (signal === 'weak') return `Faint, and ${hears}. A socket nearer a switch would be better.`
  if (signal === 'none') return `It ${hears}, and has not said how strong the link is.`
  return `Strong, and ${hears}.`
})
/* ...and the word above it. A puck on the broker that is bridging nothing is not "Working"; it is
   here, and that is all that can be said for it. */
const word = computed(() =>
  !b.value.online ? 'Quiet' : b.value.switches ? 'Working' : 'On the house')
/* "Current" is a comparison, and a hub with no manifest beside its image has nothing to compare to:
   `behind` is then false for every puck in the house, including one three versions old. Saying
   "current" off the back of that is the same mistake as calling an unseen link strong. */
const software = computed(() =>
  !b.value.fw ? 'The hub has not been told which software it runs.'
  : b.value.behind ? `${b.value.fw} — older than the house ships. It keeps working; catching it up needs a cable for now.`
  : !b.value.shipped ? `${b.value.fw}. The hub can’t say whether that is the latest.`
  : `${b.value.fw} — current.`)

async function change(what: { night?: boolean; level?: number; lift?: boolean }, tag: string) {
  if (busy.value) return
  busy.value = tag
  try { emit('changed', (await setBridgeLight(b.value.chip, what)).bridges) }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}

const asking = ref(false)
async function forget() {
  if (busy.value) return
  busy.value = 'forget'
  try {
    const r = await forgetBridge(b.value.chip)
    notify(`${r.forgotten} is no longer part of the house.`)
    emit('close')
  } catch (e: any) { notify(e.message, 'error'); busy.value = '' }
}

function key(e: KeyboardEvent) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="emit('close')">
    <div class="sheet bridge" role="dialog" :aria-label="`${b.where} bridge`">
      <div class="sheet-head">
        <h2 class="display">{{ b.where }}</h2>
        <button class="round sheet-close" @click="emit('close')" aria-label="Close"><Icon name="close" :size="20" /></button>
      </div>
      <div class="sheet-body">
        <div class="bridge-row" :class="{ good: b.online && b.signal === 'strong' }">
          <span class="bridge-icon" :class="{ good: b.online && b.signal === 'strong' }">
            <Icon :name="b.online ? 'check' : 'sparkle'" :size="18" />
          </span>
          <span class="bridge-text">
            <span class="bridge-name">{{ word }}</span>
            <span class="bridge-sub">{{ state }}</span>
          </span>
        </div>

        <ul class="hub-rows bridge-settings">
          <li v-if="!heard">
            <span class="hub-k">Its light</span>
            <span class="hub-v">Nothing said about a light yet.<span class="hub-sub line">{{ b.online ? 'This one has never offered one. Older software does not have a nightlight, and catching a bridge up needs a cable for now.' : 'Once it is back, this is where its nightlight lives.' }}</span></span>
            <span></span>
          </li>
          <template v-else>
            <li>
              <span class="hub-k">Nightlight</span>
              <span class="hub-v">A warm glow through the night.<span class="hub-sub line">It goes straight back to telling you if something is wrong, which is the point of it.</span></span>
              <button class="toggle" role="switch" :aria-checked="!!b.night" aria-label="Nightlight"
                      :class="{ on: b.night, busy: busy === 'night' }" @click="change({ night: !b.night }, 'night')"><span class="knob"></span></button>
            </li>
            <template v-if="b.night">
              <li>
                <span class="hub-k">Brightness</span>
                <span class="hub-v">How bright it rests at.<span class="hub-sub line">Its own tile dims it finer, like any light in the house.</span></span>
                <span class="bridge-levels">
                  <button v-for="l in LEVELS" :key="l.id" class="button small" :class="{ ghost: nearest !== l.id, busy: busy === l.id }"
                          @click="change({ level: l.to }, l.id)">{{ l.label }}</button>
                </span>
              </li>
              <li>
                <span class="hub-k">As you pass</span>
                <span class="hub-v">Brighten when somebody comes by.<span class="hub-sub line">It uses the switches this bridge already watches, and settles again once the room is quiet.</span></span>
                <button class="toggle" role="switch" :aria-checked="b.lift" aria-label="Brighten as you pass"
                        :class="{ on: b.lift, busy: busy === 'lift' }" @click="change({ lift: !b.lift }, 'lift')"><span class="knob"></span></button>
              </li>
            </template>
          </template>
          <li>
            <span class="hub-k">Software</span>
            <span class="hub-v">{{ software }}</span>
            <span></span>
          </li>
          <li :class="{ asking }">
            <span class="hub-k">Forget</span>
            <template v-if="!asking">
              <span class="hub-v">Take this bridge out of the house.<span class="hub-sub line">The switches it brings in go with it. Plugging it in again sets it up from the start.</span></span>
              <button class="button small" @click="asking = true">Forget</button>
            </template>
            <template v-else>
              <span class="hub-v">Forget {{ b.where.toLowerCase() }}?<span class="hub-sub line">Its switches stop working from here until a bridge is set up again.</span></span>
              <span class="bridge-levels">
                <button class="button small" :class="{ busy: busy === 'forget' }" @click="forget">Forget it</button>
                <button class="button small ghost" @click="asking = false">Keep it</button>
              </span>
            </template>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
