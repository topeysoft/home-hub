<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { addSwitch, qrUrl, moveDevice, type Letting } from './api'
import { store, notify } from './store'
import Icon from './Icon.vue'

/*
 * Letting a new wall switch in.
 *
 * One component with two faces, because it is one job done in two places. A switch out of its box
 * will not join anything until somebody proves they are holding it, and the proof is a code printed
 * on its back -- the mesh's own rule, not ours. A camera is the only way to read one, and the wall
 * panel has not got a camera. So: THE WALL SHOWS, THE PHONE SCANS. On the wall this is a code that
 * opens the phone here; on the phone it is the camera.
 *
 * Which face it wears takes two answers, not one. A browser saying it has a camera is not enough --
 * a wall panel on a Pi will happily claim one, and then it draws a viewfinder that nobody can lift
 * off the wall and hold up to a switch. So it must ALSO be something you can pick up: a hand-sized
 * screen, or a phone that got here by scanning the wall's own code, which is proof enough on its own.
 *
 * What it must never do is offer to type the code. It is 32 characters of hex. A fallback nobody
 * can complete is not a fallback.
 *
 * design/puck/Switch.dc.html and design/puck/Scan.dc.html.
 */
const emit = defineEmits<{ close: [] }>()

/* Can this thing read a code at all: a camera to point, something that can decode what it sees, and
   hands to hold it in. The first two are asked of the browser rather than assumed, because the answer
   differs per phone; the third is the 860px the rest of the panel already means by "a phone". */
const canScan = ref(false)
const decoder = ref<any>(null)
const handheld = matchMedia('(max-width: 860px)').matches || new URLSearchParams(location.search).get('add') === 'switch'
async function ableToScan() {
  if (!handheld) return false
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
const state = ref<'looking' | 'reading' | 'letting' | 'done' | 'failed'>('looking')
const said = ref('')
const got = ref<Letting | null>(null)
let stream: MediaStream | null = null
let hunting = 0

async function look() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    if (video.value) { video.value.srcObject = stream; await video.value.play() }
    state.value = 'reading'
    hunt()
  } catch {
    /* a refused camera is not a failure of the house: it is a choice, and the way through it is the
       other face of this screen -- somebody else's phone, or the code on the wall. */
    canScan.value = false
  }
}
function hunt() {
  hunting = window.setTimeout(async () => {
    if (state.value !== 'reading' || !video.value || !decoder.value) return
    try {
      const found = await decoder.value.detect(video.value)
      if (found[0]?.rawValue) return void letIn(found[0].rawValue)
    } catch {}
    hunt()
  }, 250)
}
async function letIn(code: string) {
  state.value = 'letting'
  stop()
  try {
    const r = await addSwitch(code)
    got.value = r
    state.value = r.state === 'failed' ? 'failed' : 'done'
    said.value = r.text ?? ''
  } catch (e: any) { state.value = 'failed'; said.value = e.message }
}
function stop() {
  clearTimeout(hunting)
  stream?.getTracks().forEach(t => t.stop())
  stream = null
}

/* the one question at the end. Everything else about it the house already knows from the switch. */
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const placing = ref('')
async function place(id: string) {
  if (!got.value?.device_id) return
  placing.value = id
  try { await moveDevice(got.value.device_id, id); notify(`${got.value.name || 'It'} is in the ${rooms.value.find(r => r.id === id)?.name} now.`); emit('close') }
  catch (e: any) { notify(e.message, 'error'); placing.value = '' }
}

const waiting = computed(() => store.bridge?.waiting ?? 0)
onMounted(async () => { canScan.value = await ableToScan(); if (canScan.value) look() })
onUnmounted(stop)
</script>

<template>
  <div class="flow add-switch">
    <h3 class="flow-title">Add a wall switch</h3>

    <!-- THE WALL. It cannot read the code, so its whole job is getting the phone here. -->
    <template v-if="!canScan">
      <p class="flow-desc" v-if="waiting">The bridge can already see {{ waiting === 1 ? 'one it has never met' : `${waiting} it has never met` }}. Before it lets anything in, it wants the code printed on that switch — the little square of dots on its back, or on the card that came in the box.</p>
      <p class="flow-desc" v-else>A new switch carries a code printed on its back — a little square of dots. The house needs to see that code before it will let the switch in, and this screen has no camera.</p>

      <div class="bridge-row" v-if="waiting" style="margin-bottom: 18px">
        <span class="bridge-icon" style="background: var(--lamp); color: var(--lamp-ink)"><Icon name="switch" :size="18" /></span>
        <span class="bridge-text">
          <span class="bridge-name">{{ waiting === 1 ? 'One new switch nearby' : `${waiting} new switches nearby` }}</span>
          <span class="bridge-sub">Waiting to be let in. Not on your house yet.</span>
        </span>
        <span class="pulse-dot"></span>
      </div>

      <div class="handoff">
        <div class="handoff-qr"><img :src="qrUrl(handoff)" alt="A code the phone's camera opens this step from" width="168" height="168" /></div>
        <div class="handoff-text">
          <div class="bridge-name">Point your phone at this</div>
          <p class="bridge-sub">It opens the house on your phone, already on this step, with the camera ready. Then hold the phone up to the switch’s own code.</p>
          <p class="bridge-sub">Already have the house on your phone? It is under <b>Add › Wall switch</b> there.</p>
        </div>
      </div>
      <div class="flow-actions"><button class="button ghost" @click="emit('close')">Not now</button></div>
    </template>

    <!-- THE PHONE. -->
    <template v-else-if="state === 'looking' || state === 'reading'">
      <p class="flow-desc">Point it at the square of dots — on the back of the switch, or on the card from the box.</p>
      <div class="finder">
        <video ref="video" class="finder-feed" playsinline muted></video>
        <svg class="finder-frame" viewBox="0 0 100 100" fill="none" stroke="rgba(255,255,255,.92)" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
          <path d="M22 34v-8a4 4 0 0 1 4-4h8" /><path d="M66 22h8a4 4 0 0 1 4 4v8" />
          <path d="M22 66v8a4 4 0 0 0 4 4h8" /><path d="M78 66v8a4 4 0 0 1-4 4h-8" />
        </svg>
      </div>
      <div class="flow-actions"><button class="button ghost" @click="stop(); emit('close')">Cancel</button></div>
    </template>

    <template v-else-if="state === 'letting'">
      <p class="flow-desc pulse">Got it. Letting it into the house — it learns the house’s keys, then says hello to the bridge.</p>
      <div class="bridge-bar"><i style="width: 52%"></i></div>
      <p class="sheet-status">Around half a minute. You can put your phone down.</p>
    </template>

    <template v-else-if="state === 'done'">
      <p class="flow-done"><span class="done-icon"><Icon name="check" :size="20" /></span>It’s in. {{ said || 'A light that dims, and a motion sensor.' }}</p>
      <template v-if="got?.device_id">
        <p class="flow-desc">Which room is it in?</p>
        <div class="press-rooms">
          <button v-for="r in rooms" :key="r.id" class="chip-btn" :class="{ on: placing === r.id }" @click="place(r.id)">{{ r.name }}</button>
        </div>
        <div class="flow-actions"><button class="button ghost" @click="emit('close')">Later</button></div>
      </template>
      <div class="flow-actions" v-else><button class="button" @click="emit('close')">Done</button></div>
    </template>

    <template v-else>
      <p class="flow-desc">{{ said || 'That code was not one this house could use.' }}</p>
      <div class="flow-actions">
        <button class="button" @click="state = 'reading'; look()">Try again</button>
        <button class="button ghost" @click="emit('close')">Not now</button>
      </div>
    </template>
  </div>
</template>
