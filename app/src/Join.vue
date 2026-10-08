<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getMe, askToJoin, claimJoin, joinWithCode } from './api'
import { lock, remember } from './code'
import Icon from './Icon.vue'
import { isScreen } from './screen'

/* The house has a code and this device is not one of its phones yet. Two ways in: ask, and someone at a screen that
   is already in taps Allow (and types the passcode); or type the passcode here. Being on the Wi‑Fi alone gets nothing. */
const emit = defineEmits<{ joined: [] }>()
const home = ref('the house'), who = ref(''), code = ref(''), mode = ref<'ask' | 'code'>('ask'), error = ref(''), busy = ref(false), asked = ref<string | null>(null)
const ua = navigator.userAgent
const device = /iPad/.test(ua) || (/Macintosh/.test(ua) && 'ontouchend' in document) ? 'iPad' : /iPhone/.test(ua) ? 'iPhone'
  : /Android/.test(ua) ? (/Mobile/.test(ua) ? 'Android phone' : 'Android tablet') : matchMedia('(max-width: 860px)').matches ? 'phone' : 'screen'
/* A screen on the wall is nobody's, so it is not asked for a name: it takes its room's once it has one (design/companion/, C). */
const screen = isScreen()
const name = computed(() => { if (screen) return 'A screen'; const w = who.value.trim(); return w ? `${w}'s ${device}` : `A ${device}` })
let poll: number | undefined
const preview = new URLSearchParams(location.search).get('join') === '1'   // ?join=1 keeps the screen up against a hub that would let this device in
onMounted(async () => { try { const me = await getMe(); home.value = me.home; if (me.paired && !preview) done() } catch {} })
onUnmounted(() => clearInterval(poll))
function done() { clearInterval(poll); lock.unpaired = false; emit('joined') }
async function ask() {
  if (busy.value) return
  error.value = ''; busy.value = true
  try { const a = await askToJoin(name.value, screen ? 'screen' : undefined); asked.value = a.id; poll = window.setInterval(check, 2000) } catch (e: any) { error.value = e.message }
  busy.value = false
}
async function check() {
  if (!asked.value) return
  try {
    const c = await claimJoin(asked.value)
    if (c.state === 'allowed') done()
    else if (c.state === 'gone') { clearInterval(poll); asked.value = null; error.value = 'Not this time. Ask again, or type the passcode.' }
  } catch {}
}
function cancel() { clearInterval(poll); asked.value = null }
async function withCode() {
  if (busy.value) return
  error.value = ''
  if (!/^\d{4,8}$/.test(code.value)) { error.value = 'A passcode is 4 to 8 digits.'; return }
  busy.value = true
  try { await joinWithCode(code.value, name.value, screen ? 'screen' : undefined); remember(code.value); done() } catch (e: any) { error.value = e.message }
  busy.value = false
}
</script>

<template>
  <main class="setup join">
    <section class="setup-page" v-if="screen">
      <span class="setup-mark"><Icon name="home" :size="30" /></span>
      <h1 class="display">This screen is for {{ home }}.</h1>
      <template v-if="!asked">
        <p class="setup-lede">Its hub is on this Wi‑Fi. Type the house passcode to finish.</p>
        <input class="input code-input screen-code" v-model="code" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" maxlength="8" placeholder="••••" aria-label="The passcode" @keydown.enter="withCode" />
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions">
          <button class="button big" :class="{ busy }" :disabled="code.length < 4" @click="withCode">Continue</button>
          <button class="button ghost big" @click="ask">Ask from another screen</button>
        </div>
      </template>
      <template v-else>
        <p class="setup-lede">Asked. Say yes on a phone or another screen in the house, and this one opens by itself.</p>
        <p class="setup-status"><span class="pulse-dot"></span> Waiting for a yes…</p>
        <p class="setup-foot"><button class="linkish" @click="cancel">Type the passcode instead</button></p>
      </template>
    </section>
    <section class="setup-page" v-else>
      <span class="setup-mark"><Icon name="phone" :size="30" /></span>
      <h1 class="display">Join {{ home }}.</h1>
      <template v-if="!asked">
        <p class="setup-lede">This {{ device }} is new here. Someone at the wall screen can allow it, or you can type the house's passcode.</p>
        <label class="field"><span class="field-label">Your name <span class="field-opt">· so the house knows whose this is</span></span>
          <input class="input" v-model="who" autocomplete="given-name" autocapitalize="words" placeholder="Sam" @keydown.enter="mode === 'code' ? withCode() : ask()" /></label>
        <label class="field" v-if="mode === 'code'"><span class="field-label">The passcode</span>
          <input class="input code-input" v-model="code" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" maxlength="8" placeholder="••••" @keydown.enter="withCode" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions" v-if="mode === 'ask'">
          <button class="button big" :class="{ busy }" @click="ask">Ask to join</button>
          <button class="button ghost" @click="mode = 'code'; error = ''">I know the passcode</button>
        </div>
        <div class="setup-actions" v-else>
          <button class="button big" :class="{ busy }" :disabled="code.length < 4" @click="withCode">Join</button>
          <button class="button ghost" @click="mode = 'ask'; error = ''">Ask instead</button>
        </div>
        <p class="setup-foot">Connect to your home Wi‑Fi first. You can see and remove phones any time in <i>People</i>.</p>
      </template>
      <template v-else>
        <p class="setup-lede">Asked as <b>{{ name }}</b>. On the wall screen, or on a phone that already uses the house, tap <b>Allow</b>.</p>
        <p class="setup-status"><span class="pulse-dot"></span> Waiting for someone to answer…</p>
        <div class="setup-actions"><button class="button ghost" @click="cancel">Cancel</button></div>
      </template>
    </section>
  </main>
</template>
