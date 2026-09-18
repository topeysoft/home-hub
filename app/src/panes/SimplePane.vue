<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The kinds whose whole instrument is one control: a plug, a fan, a mower, an alarm.
 *
 * A plug gets an on and a for-how-long, because a coffee maker and a heater are what a plug is
 * usually holding. A fan gets three named speeds, because nobody standing at a wall panel picks
 * thirty-seven per cent. A mower has nowhere to go but out and back.
 *
 * The timer is the hub's, not the driver's: POST /devices/<id>/timer, the same shape as the
 * thermostat's fan. A restart forgets it and what is left behind is a thing that is simply on.
 *
 * An alarm is a plug with two things taken away and one added, and each of the three is the
 * point. It asks twice before it sounds (twice.ts). It has no for-how-long, because "sound the
 * siren for an hour" is not a sentence anybody meant to say and the row of cards offered it in
 * one tap. And it says sound and silence rather than on and off, so the button reads as what it
 * does to a house rather than what it does to a circuit.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Device } from '../api'
import { runFor } from '../api'
import { cap, guessNow, isDead, notify, perform } from '../store'
import { useArm } from '../twice'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const kind = computed(() => cap(props.device))
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const on = computed(() => props.device.state === 'on')

/* ---- a plug, and anything else that is simply on or off ---- */
const now = ref(Date.now())
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 15000) })
onUnmounted(() => clearInterval(tick))
const until = computed(() => a.value.off_at as number | undefined)
const left = computed(() => until.value ? Math.max(0, Math.round((until.value * 1000 - now.value) / 60000)) : null)
const busy = ref(false)
const FOR = [10, 30, 60]
async function timer(minutes: number) {
  if (dead.value || busy.value) return
  busy.value = true
  try {
    const r = await runFor(props.device.id, minutes)
    guessNow(props.device, { state: minutes ? 'on' : undefined, attrs: { off_at: r.off_at ?? undefined } })
    if (minutes) notify(`On for ${minutes < 60 ? `${minutes} minutes` : 'an hour'}.`)
    else notify('It will stay on until somebody switches it off.')
  } catch (e: any) { notify(`Couldn't set the timer: ${e.message}`, 'error') }
  busy.value = false
}

/* ---- a fan: three speeds with names ---- */
const SPEEDS = [{ name: 'Low', pct: 33 }, { name: 'Medium', pct: 66 }, { name: 'High', pct: 100 }]
const speed = computed(() => !on.value ? '' : SPEEDS.reduce((best, s) =>
  Math.abs(s.pct - (a.value.percentage ?? 100)) < Math.abs(best.pct - (a.value.percentage ?? 100)) ? s : best).name)
const hasSpeed = computed(() => a.value.percentage != null)
const setSpeed = (s: { name: string; pct: number }) =>
  perform(props.device, hasSpeed.value ? 'set' : 'on', hasSpeed.value ? { percentage: s.pct } : undefined, { state: 'on', attrs: { percentage: s.pct } })

/* ---- an alarm: the same one button, and it asks first ---- */
const { armed, tap: armedTap } = useArm()
const sound = () => armedTap(kind.value, on.value ? 'off' : 'on',
  () => perform(props.device, on.value ? 'off' : 'on', undefined, { state: on.value ? 'off' : 'on' }))

/* ---- a mower or a vacuum: out, and back ---- */
const out = computed(() => props.device.state === 'cleaning')
const heading = computed(() => props.device.state === 'returning')
</script>

<template>
  <div class="rig rig-simple">
    <!-- a fan -->
    <template v-if="kind === 'fan'">
      <div class="rig-speeds">
        <button v-for="s in SPEEDS" :key="s.name" class="rig-speed" :class="{ on: on && speed === s.name }" :disabled="dead" @click="setSpeed(s)">
          <!-- the bars are the board's 34/62/92, in px: as a percentage of the cell they grew with
               the pane until Low looked like plenty -->
          <span class="rig-speed-bar" :style="{ height: Math.round(s.pct * 0.92) + 'px' }"></span>
          <span class="rig-speed-name">{{ s.name }}</span>
        </button>
      </div>
      <button class="rig-btn wide" :disabled="dead" @click="perform(device, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' })">
        <Icon name="power" :size="20" /><span>{{ on ? 'Switch it off' : 'Switch it on' }}</span>
      </button>
    </template>

    <!-- an alarm: one button, armed, and nothing beside it to press by mistake -->
    <template v-else-if="kind === 'alarm'">
      <button class="rig-big" :class="{ on, arming: !!armed }" :disabled="dead" @click="sound">
        <Icon name="alarm" :size="24" /><span>{{ armed || (on ? 'Silence it' : 'Sound it') }}</span>
      </button>
    </template>

    <!-- a mower, a vacuum -->
    <template v-else-if="kind === 'vacuum'">
      <button class="rig-big" :class="{ on: out }" :disabled="dead || out" @click="perform(device, 'start', undefined, { state: 'cleaning' })">
        <Icon name="play" :size="24" /><span>{{ out ? 'It is out working' : 'Send it out' }}</span>
      </button>
      <button class="rig-btn wide" :disabled="dead || heading" @click="perform(device, 'return', undefined, { state: 'returning' })">
        <Icon name="home" :size="20" /><span>{{ heading ? 'On its way back' : 'Back to the dock' }}</span>
      </button>
    </template>

    <!-- a plug, and anything else with nothing but an on -->
    <template v-else>
      <button class="rig-big" :class="{ on }" :disabled="dead" @click="perform(device, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' })">
        <Icon name="power" :size="24" /><span>{{ on ? 'Switch it off' : 'Switch it on' }}</span>
      </button>
      <!-- and for a while: the same cards the board drew, one row of equal ones. Not for an appliance:
           "ice maker for 10 minutes" is a plug's sentence, and a fridge's feature is on until it is not -->
      <div class="rig-timer" v-if="kind === 'appliance'"></div>
      <div class="rig-timer" v-else-if="left == null">
        <button v-for="m in FOR" :key="m" class="rig-when" :disabled="dead || busy" @click="timer(m)">for {{ m < 60 ? `${m} min` : 'an hour' }}</button>
      </div>
      <div class="rig-timer one" v-else>
        <span class="rig-when said">Off again in {{ left < 1 ? 'under a minute' : `${left} min` }}</span>
        <button class="rig-when" :disabled="busy" @click="timer(0)">Leave it on</button>
      </div>
    </template>
  </div>
</template>
