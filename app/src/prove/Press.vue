<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { startPair, getPair, pairPin, stopPair, type Pair } from '../api'
import { everyDevice, pressRadios, matterUp, whatArrived, type Act, type Caught, type Working } from '../adding'

/*
 * PRESS IT. Beat two for a thing out of a box: a plug, a bulb, a sensor, a remote.
 *
 * THE RADIO IS NOT THE QUESTION. Somebody holding a plug cannot tell you whether it is Zigbee or
 * Z-Wave, and should never be asked: the hub is the only one in the house that knows, so the hub
 * works it out. It opens each radio it has in turn while this screen is up, and the screen says one
 * thing throughout -- press its button. A device left in pairing mode is caught on the next pass.
 *
 * Matter is the exception and it is not one a person has to understand either: a Matter thing has a
 * code printed on it, and a code is a thing you can SEE. So it is offered as "it came with a QR
 * code", which is a question about the object in their hand, and it hands over to the code piece.
 *
 * Draws its middle and nothing else. design/adding/Proving.dc.html.
 */
const emit = defineEmits<{ working: [Working], caught: [Caught], wrong: [string, boolean?], acts: [Act[]], proof: [string, string?] }>()

const radios = pressRadios()
const SLICE = 60_000            // how long each radio's door stays open before the next one's turn

const pair = ref<Pair>({ state: 'idle' })
const pin = ref(''), error = ref('')
const at = ref(0)               // which radio's turn it is
const rotating = ref(false)
const before = everyDevice()
let poll: number | undefined, turned = 0, holding = false

const live = computed(() => ['listening', 'found', 'pin', 'working'].includes(pair.value.state))

async function openDoor(i: number) {
  at.value = i % radios.length
  rotating.value = true
  turned = Date.now()
  try { pair.value = await startPair(radios[at.value]) } catch (e: any) { return emit('wrong', e.message, true) }
  rotating.value = false
  watchIt()
}
function watchIt() { clearTimeout(poll); poll = window.setTimeout(refresh, 1500) }
async function refresh() {
  if (rotating.value) return watchIt()
  try { pair.value = await getPair() } catch { return watchIt() }
  const s = pair.value.state
  if (s === 'done') return void arrived()
  /* Something is part-way in. The screen stops asking for a press and starts reporting, because the
     press has already happened -- beat three begins the moment the house has hold of something. */
  if (s === 'found' && !holding) { holding = true; emit('working', { text: 'Letting it in…', how_long: 'A few seconds while the house works out what it is.' }) }
  if (s === 'failed') return emit('wrong', pair.value.text ?? 'That did not work.', true)
  if (s === 'closed') {
    /* the window ran out on its own. With one radio that is the end of the conversation; with two it
       is simply the other one's turn, which is nothing a person needs told about. */
    if (radios.length > 1) return void openDoor(at.value + 1)
    return emit('wrong', pair.value.text ?? 'Nothing joined. Put the device in pairing mode and try again.', true)
  }
  /* time for the other radio, if there is one and nothing is part-way through joining */
  if (s === 'listening' && radios.length > 1 && Date.now() - turned > SLICE) return void openDoor(at.value + 1)
  watchIt()
}

/* It joined a radio, which means it is in Home Assistant and lands in the house a moment later. Beat
   four needs the thing itself, so this waits for it rather than sending somebody off to find it. */
async function arrived() {
  clearTimeout(poll)
  if (!holding) emit('working', { text: 'Letting it in…', how_long: 'A few seconds while the house works out what it is.' })
  const c = await whatArrived(before)
  emit('caught', c.device_id ? c : { ...c, name: pair.value.device?.name ?? undefined })
}

async function sendPin() {
  error.value = ''
  try { pair.value = await pairPin(pin.value.trim()); pin.value = '' } catch (e: any) { error.value = e.message }
}

const code = { label: 'It came with a QR code', run: () => emit('proof', 'code', 'matter') }
watch(pair, p => {
  if (p.needs === 'pin') emit('acts', [{ label: 'Continue', primary: true, run: sendPin }])
  else emit('acts', matterUp() ? [code] : [])
}, { immediate: true, deep: true })

onMounted(() => { if (radios.length) openDoor(0); else emit('proof', 'code', 'matter') })
onUnmounted(() => { clearTimeout(poll); if (live.value) stopPair().catch(() => {}) })
</script>

<template>
  <p class="flow-desc">Press its button now. Most of them want one long press, or switching off and on three times &mdash; the box will say.</p>

  <div class="press-line" style="margin-bottom: 14px">
    <span class="press-said"><span class="pulse-dot"></span>{{ pair.state === 'found' ? pair.text : 'The house is listening' }}</span>
  </div>

  <template v-if="pair.needs === 'pin'">
    <label class="field">
      <span class="field-label">The 5&#8209;digit code on its sticker</span>
      <input class="input code-input" v-model="pin" inputmode="numeric" pattern="[0-9]*" maxlength="5" autocomplete="off" @keydown.enter="sendPin" />
    </label>
    <p class="error" v-if="error">{{ error }}</p>
  </template>
  <p class="sheet-status" v-else>It stops listening on its own after a few minutes.</p>
</template>
