<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { nearbySwitches, blinkSwitch, letSwitchIn, type Waiting } from '../api'
import { asThing, type Act, type Caught, type Working } from '../adding'
import Icon from '../Icon.vue'

/*
 * IT BLINKS. Beat two for a switch that is already screwed to a wall.
 *
 * The code on a switch's back is not a password -- what it buys is knowing WHICH switch, and a switch
 * on a wall has its code facing the plasterboard. So it is proved by the switch instead: the house
 * asks what is waiting, makes one announce itself, and a person says whether the blinking one is the
 * one they just touched. THE IDENTITY CHECK IS THE OBJECT, NOT A NUMBER -- which is also why this
 * needs no camera, and runs on the wall exactly as it runs on a phone.
 *
 * It blinks them ONE AT A TIME. A room with two blinking switches in it answers nothing.
 *
 * Draws its middle and nothing else: the title, the buttons and the ending are the shell's.
 * design/adding/Proving.dc.html, and design/puck/Held.dc.html before it.
 */
const emit = defineEmits<{ working: [Working], caught: [Caught], wrong: [string, boolean?], acts: [Act[]], proof: [string, string?] }>()

const step = ref<'looking' | 'none' | 'asking'>('looking')
const waiting = ref<Waiting[]>([])
const spokenFor = ref<Waiting[]>([])
const at = ref(0)
const said = ref('')

const here = computed(() => waiting.value[at.value])
const more = computed(() => waiting.value.length - at.value - 1)

async function look() {
  step.value = 'looking'; said.value = ''
  emit('acts', [])
  try {
    const r = await nearbySwitches()
    if (r.state === 'failed') return emit('wrong', r.text ?? 'The house could not listen for switches.', true)
    waiting.value = r.waiting ?? []
    spokenFor.value = r.claimed_elsewhere ?? []
    at.value = 0
    if (!waiting.value.length) { step.value = 'none'; said.value = r.text ?? ''; return }
    await offer()
  } catch (e: any) { emit('wrong', e.message, true) }
}

/* Blink the one being offered. If it cannot be reached there is nothing honest left to ask about it,
   so that is a failure of this candidate rather than of the whole job: move on. */
async function offer() {
  const who = here.value
  if (!who?.uuid) { step.value = 'none'; return }
  step.value = 'asking'
  try { await blinkSwitch(who.uuid, 5) } catch { /* it may still be the right one; let them look */ }
}

function notThisOne() {
  if (more.value > 0) { at.value++; offer() }
  else { step.value = 'none'; said.value = 'That was the last one it could hear.' }
}

async function yesThatOne() {
  const who = here.value
  if (!who?.uuid) return
  emit('working', { text: 'Letting it in…', how_long: 'Around half a minute. You can put your phone down.' })
  try {
    const r = await letSwitchIn(who.uuid)
    if (r.state === 'failed') return emit('wrong', r.text ?? 'That switch would not join.', true)
    emit('caught', { device_id: r.device_id, name: r.name, what: asThing(r.text) || 'a light that dims, and a motion sensor' })
  } catch (e: any) { emit('wrong', e.message, true) }
}

/* What this piece needs offering, in the state it is in. The shell puts them in order and adds the
   way out; the words themselves are the house's, not this screen's. */
const theCode = { label: 'I can reach the code', run: () => emit('proof', 'code', 'switch') }
watch([step, more], () => {
  if (step.value === 'asking') emit('acts', [
    { label: 'That’s the one', primary: true, run: yesThatOne },
    { label: more.value > 0 ? 'Try the next one' : 'No, none of them', run: notThisOne },
  ])
  else if (step.value === 'none') emit('acts', [{ label: 'Look again', primary: true, run: look }, theCode])
  else emit('acts', [])
}, { immediate: true })

onMounted(look)
</script>

<template>
  <p class="flow-desc pulse" v-if="step === 'looking'">Listening for a switch that is asking to be let in…</p>

  <!-- nothing claimable, which is two situations wanting opposite things said -->
  <template v-else-if="step === 'none'">
    <p class="flow-desc">{{ said || 'Nothing nearby is asking to be let in.' }}</p>
    <div class="bridge-row" v-if="spokenFor.length" style="margin-bottom: 18px">
      <span class="bridge-icon"><Icon name="switch" :size="18" /></span>
      <span class="bridge-text">
        <span class="bridge-name">{{ spokenFor.length === 1 ? 'One is on another network' : `${spokenFor.length} are on another network` }}</span>
        <span class="bridge-sub">Pull its little tab out and push it back, then hold a finger flat on it until it blinks. Then look again.</span>
      </span>
    </div>
    <p class="flow-desc" v-else>A switch out of a box is already asking, with nothing to press. One that has been set up before needs its tab pulled out and pushed back, then a finger held on it until it blinks.</p>
  </template>

  <!-- the identity check: one blinking switch, one question -->
  <template v-else>
    <p class="flow-desc">{{ waiting.length === 1 ? 'One switch is waiting.' : `${waiting.length} switches are waiting.` }} It should be blinking now.</p>
    <div class="press-line" style="margin-bottom: 18px">
      <span class="press-said"><span class="pulse-dot"></span>Is the blinking one the switch you just touched?</span>
    </div>
    <p class="sheet-status" v-if="more > 0">{{ more }} more it can hear.</p>
    <p class="sheet-status" v-else-if="waiting.length > 1">The last one it can hear.</p>
  </template>
</template>
