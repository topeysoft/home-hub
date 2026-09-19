<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { addSwitch, startPair, getPair, stopPair, qrUrl } from '../api'
import { asThing, everyDevice, whatArrived, type Act, type Caught, type Working } from '../adding'

/*
 * READ ITS CODE. Beat two for anything whose proof is printed on it.
 *
 * Two things arrive that way and they are not the same job. A MATTER thing has its code where you can
 * read it, in the box or on the case, and the code is short enough to type. A SWITCH has 32 characters
 * of hex on its back, which nobody can type and a camera must read -- so that half is a camera, and
 * a wall panel has not got one.
 *
 * THE WALL SHOWS, THE PHONE SCANS. Which face this wears takes two answers, not one: a browser saying
 * it has a camera is not enough, because a panel on a Pi will happily claim one and then draw a
 * viewfinder nobody can lift off the wall. So it must ALSO be something you can pick up -- a
 * hand-sized screen, or a phone that got here by scanning the wall's code, which is proof on its own.
 *
 * What it must never do is offer to type the switch's code. A fallback nobody can complete is not one.
 *
 * design/adding/Proving.dc.html, and design/puck/Scan.dc.html before it.
 */
const props = defineProps<{ on?: string | null }>()
const emit = defineEmits<{ working: [Working], caught: [Caught], wrong: [string, boolean?], acts: [Act[]], proof: [string, string?] }>()
const matter = props.on === 'matter'

/* ---- the Matter half: a code short enough to be read out and typed ---- */
const typed = ref(''), error = ref(''), joining = ref(false)
const before = everyDevice()
let poll: number | undefined
async function addTyped() {
  if (!typed.value.trim()) { error.value = 'The code on the device is needed.'; return }
  error.value = ''
  emit('working', { text: 'Letting it in…', how_long: 'Up to a minute. It talks to the house over your Wi‑Fi.' })
  try {
    const p = await startPair('matter', typed.value.trim())
    joining.value = true
    if (p.state === 'failed') return emit('wrong', p.text ?? 'That code was not one this house could use.', true)
    watchIt()
  } catch (e: any) { emit('wrong', e.message, true) }
}
function watchIt() { clearTimeout(poll); poll = window.setTimeout(async () => {
  let p; try { p = await getPair() } catch { return watchIt() }
  if (p.state === 'done') return void arrived()
  if (p.state === 'failed' || p.state === 'closed') { joining.value = false; return emit('wrong', p.text ?? 'It did not join.', true) }
  watchIt()
}, 1500) }
async function arrived() { clearTimeout(poll); joining.value = false; emit('caught', await whatArrived(before)) }

/* ---- the switch half: a camera, or the phone that has one ---- */
const canScan = ref(false)
const decoder = ref<any>(null)
const handheld = matchMedia('(max-width: 860px)').matches || new URLSearchParams(location.search).get('add') === 'switch'
async function ableToScan() {
  if (matter || !handheld) return false
  if (!navigator.mediaDevices?.getUserMedia) return false
  const BD = (window as any).BarcodeDetector
  if (!BD) return false
  try {
    const kinds: string[] = await BD.getSupportedFormats()
    if (!kinds.includes('qr_code')) return false
    decoder.value = new BD({ formats: ['qr_code'] })
    return true
  } catch { return false }
}
/* the address the phone should open, and the step it should land on */
const here = location.hostname.endsWith('.local') || /^\d+\.\d+\.\d+\.\d+$/.test(location.hostname)
  ? `${location.protocol}//${location.host}` : 'http://hub.local'
const handoff = `${here}/?add=switch`

const video = ref<HTMLVideoElement | null>(null)
let stream: MediaStream | null = null
let hunting = 0
async function look() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    if (video.value) { video.value.srcObject = stream; await video.value.play() }
    hunt()
  } catch {
    /* a refused camera is not a failure of the house: it is a choice, and the way through it is the
       other half of this screen -- somebody else's phone, or the switch blinking on the wall. */
    canScan.value = false
  }
}
function hunt() {
  hunting = window.setTimeout(async () => {
    if (!video.value || !decoder.value) return
    try {
      const found = await decoder.value.detect(video.value)
      if (found[0]?.rawValue) return void letIn(found[0].rawValue)
    } catch {}
    hunt()
  }, 250)
}
async function letIn(code: string) {
  stop()
  emit('working', { text: 'Letting it in…', how_long: 'Around half a minute. You can put your phone down.' })
  try {
    const r = await addSwitch(code)
    if (r.state === 'failed') return emit('wrong', r.text ?? 'That code was not one this house could use.', true)
    emit('caught', { device_id: r.device_id, name: r.name, what: asThing(r.text) || 'a light that dims, and a motion sensor' })
  } catch (e: any) { emit('wrong', e.message, true) }
}
function stop() { clearTimeout(hunting); stream?.getTracks().forEach(t => t.stop()); stream = null }

const noCode = { label: 'No code on the back?', run: () => { stop(); emit('proof', 'blink') } }
watch([canScan, typed], () => {
  if (matter) emit('acts', [{ label: 'Add it', primary: true, run: addTyped }])
  else emit('acts', [noCode])
}, { immediate: true })

onMounted(async () => { canScan.value = await ableToScan(); if (canScan.value) look() })
/* Walking out on a Matter thing half way in shuts the door behind you: the hub is left listening
   otherwise, and the next person to add something finds a door they did not open. */
onUnmounted(() => { stop(); clearTimeout(poll); if (joining.value) stopPair().catch(() => {}) })
</script>

<template>
  <!-- Matter: the code is on the box, and it is short -->
  <template v-if="matter">
    <p class="flow-desc">Matter things carry a code printed under their QR square, on the case or in the box. Type it here, with the thing powered on and nearby.</p>
    <label class="field">
      <span class="field-label">The code printed on it</span>
      <input class="input" v-model="typed" placeholder="e.g. 3497-011-2332 or MT:…" autocomplete="off" autocapitalize="characters" spellcheck="false" @keydown.enter="addTyped" />
    </label>
    <p class="error" v-if="error">{{ error }}</p>
  </template>

  <!-- a switch, on something you can hold -->
  <template v-else-if="canScan">
    <p class="flow-desc">Point it at the square of dots &mdash; on the back of the switch, or on the card from the box.</p>
    <div class="finder">
      <video ref="video" class="finder-feed" playsinline muted></video>
      <svg class="finder-frame" viewBox="0 0 100 100" fill="none" stroke="rgba(255,255,255,.92)" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
        <path d="M22 34v-8a4 4 0 0 1 4-4h8" /><path d="M66 22h8a4 4 0 0 1 4 4v8" />
        <path d="M22 66v8a4 4 0 0 0 4 4h8" /><path d="M78 66v8a4 4 0 0 1-4 4h-8" />
      </svg>
    </div>
    <p class="sheet-status"><span class="pulse-dot"></span> Looking…</p>
  </template>

  <!-- a switch, on the wall: it cannot hold a camera, so it hands the job over -->
  <template v-else>
    <p class="flow-desc">A switch carries its code on its back &mdash; a little square of dots. The house needs to see that code, and this screen has no camera.</p>
    <div class="handoff">
      <div class="handoff-qr"><img :src="qrUrl(handoff)" alt="A code the phone's camera opens this step from" width="168" height="168" /></div>
      <div class="handoff-text">
        <div class="bridge-name">Point your phone at this</div>
        <p class="bridge-sub">It opens the house on your phone, already on this step, with the camera ready. Then hold the phone up to the switch’s own code.</p>
        <p class="bridge-sub">Already have the house on your phone? It is under <b>Add › A switch on the wall</b> there.</p>
      </div>
    </div>
  </template>
</template>
