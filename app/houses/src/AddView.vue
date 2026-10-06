<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Adding a house (design/houses/, The app: AppSafari, AppFirst, AppName).
 *
 * A house is carried in by the move the house's own screen starts: /add#h=<house>&c=<code>. Anywhere a page
 * keeps what it was given, the code is claimed at once. On an iPhone in Safari it is not, because the Home
 * Screen app keeps its own storage and anything added here would never reach it: the code is shown to carry
 * across instead (carry), and the Home Screen app asks for it (code). Then the phone names the house (name).
 */
import { computed, onMounted, ref } from 'vue'
import { add, addLink, claim, codeOf, iphoneSafari, labelOf, nearby, originOf, standalone, state } from './houses'

const emit = defineEmits<{ added: [id: string]; cancel: [] }>()

const mode = ref<'carry' | 'code' | 'name'>('code')
const link = ref<{ house: string; code: string } | null>(null)
const typed = ref('')
const address = ref('')
const near = ref<string[]>([])
const busy = ref(false)
const error = ref('')
const got = ref<{ id: string; origin: string; token: string; lan: string | null } | null>(null)
const name = ref('')
const zone = location.hostname.split('.').slice(1).join('.') || 'elyir.app'

const cells = computed(() => {
  const c = codeOf(typed.value).slice(0, 8).padEnd(8, ' ')
  return [...c]
})

async function take(house: string, code: string): Promise<boolean> {
  const origin = originOf(house, location, import.meta.env.VITE_HOUSE || undefined)
  try {
    const r = await claim(origin, code)
    got.value = { id: house, origin, token: r.token, lan: r.lan }
    const first = !state.houses.length
    name.value = first ? 'Home' : (r.home && r.home !== 'Home' ? r.home : '')
    mode.value = 'name'
    return true
  } catch (e: any) { error.value = e.message; return false }
}

/* The typed code, tried at the house it was for: one named by its address, or the houses on this Wi-Fi in turn. */
async function submit() {
  const code = codeOf(typed.value)
  if (code.length !== 8 || busy.value) return
  busy.value = true; error.value = ''
  const where = address.value.trim() ? [labelOf(address.value)] : near.value
  if (!where.length) { error.value = 'Which house is it? Type its web address.'; busy.value = false; return }
  for (const h of where) if (await take(h, code)) break
  busy.value = false
}

async function finish() {
  if (!got.value) return
  const g = got.value
  await add({ id: g.id, name: name.value.trim() || 'Home', origin: g.origin, lan: g.lan ?? '', token: g.token, added: Date.now(), opened: Date.now() })
  emit('added', g.id)
}

function justSafari() { if (link.value) { busy.value = true; take(link.value.house, link.value.code).finally(() => { busy.value = false }) } }

onMounted(async () => {
  link.value = addLink(location.hash)
  if (location.hash) history.replaceState(null, '', location.pathname)        // nothing keeps a code it was handed
  if (link.value) {
    if (iphoneSafari(navigator.userAgent, standalone())) { mode.value = 'carry'; return }
    busy.value = true
    const ok = await take(link.value.house, link.value.code)
    busy.value = false
    if (ok) return
  }
  mode.value = 'code'
  near.value = (await nearby(location)).filter(n => !state.houses.some(h => h.id === n))
})
</script>

<template>
  <div class="hs-field"></div>

  <!-- AppSafari: nothing is added in Safari on an iPhone; the code goes with you -->
  <main class="hs-page" v-if="mode === 'carry' && link">
    <span class="hs-mark"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M4 11l8-6 8 6v8a1 1 0 01-1 1H5a1 1 0 01-1-1z"/></svg></span>
    <h1 class="hs-title">Add Houses to your Home Screen.</h1>
    <p class="hs-lede">On iPhone the Home Screen app keeps its own things, so the house goes in there, with this code.</p>
    <div class="hs-carry">
      <span class="hs-carry-say">Your code · works for 10 minutes</span>
      <div class="hs-code" aria-label="The code">
        <template v-for="(c, i) in link.code" :key="i"><i>{{ c }}</i><i class="gap" v-if="i === 3"></i></template>
      </div>
    </div>
    <ol class="hs-steps">
      <li><span class="n">1</span><span><b>Share, then Add to Home Screen</b></span></li>
      <li><span class="n">2</span><span><b>Open Houses</b><span class="s">It asks for the code.</span></span></li>
    </ol>
    <p class="hs-error" v-if="error">{{ error }}</p>
    <button class="hs-link" :disabled="busy" @click="justSafari">Just use Safari</button>
  </main>

  <!-- AppFirst: the code the house showed, and the houses on this Wi-Fi -->
  <main class="hs-page" v-else-if="mode === 'code'">
    <h1 class="hs-title">Add a house</h1>
    <p class="hs-lede">Type the code the house showed you.</p>
    <label class="hs-code">
      <template v-for="(c, i) in cells" :key="i"><i :class="{ next: i === codeOf(typed).length }">{{ c }}</i><i class="gap" v-if="i === 3"></i></template>
      <input v-model="typed" maxlength="11" autocomplete="one-time-code" autocapitalize="characters" spellcheck="false" aria-label="The code" @keyup.enter="submit" @input="codeOf(typed).length === 8 && submit()" />
    </label>
    <p class="hs-small">No code? On the house’s screen, open This house, then Add this phone to Houses.</p>
    <template v-if="near.length">
      <p class="hs-cap">On this Wi‑Fi</p>
      <div class="hs-near" v-for="n in near" :key="n">
        <span class="hs-icon"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M4 11l8-6 8 6v8a1 1 0 01-1 1H5a1 1 0 01-1-1z"/></svg></span>
        <span><span class="hs-near-t">{{ n }}.{{ zone }}</span><span class="hs-near-s">A house on the Wi‑Fi you’re on</span></span>
        <a class="hs-pill" :href="`https://${n}.${zone}/`" target="_blank" rel="noopener">Open</a>
      </div>
      <p class="hs-small">Opening it shows the code on the house’s own screen.</p>
    </template>
    <template v-else>
      <p class="hs-cap">Which house</p>
      <input class="hs-field-input" v-model="address" :placeholder="`yourhouse.${zone}`" autocapitalize="none" spellcheck="false" aria-label="The house’s web address" />
    </template>
    <p class="hs-error" v-if="error">{{ error }}</p>
    <div class="hs-actions">
      <button class="hs-btn wide" :disabled="busy || codeOf(typed).length !== 8" @click="submit">Add it</button>
      <button class="hs-btn ghost" v-if="state.houses.length" @click="emit('cancel')">Not now</button>
    </div>
  </main>

  <!-- AppName: the phone's name for it -->
  <main class="hs-page" v-else-if="mode === 'name'">
    <span class="hs-mark done"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>
    <h1 class="hs-title">Added.</h1>
    <p class="hs-lede">What do you call this house? Only this phone sees the name.</p>
    <input class="hs-field-input" style="margin-top: 22px" v-model="name" maxlength="40" aria-label="What you call this house" @keyup.enter="finish" />
    <div class="hs-chips">
      <button class="hs-chip" v-for="n in ['Home', 'Lake house', 'Cabin', 'Mom’s']" :key="n" @click="name = n">{{ n }}</button>
    </div>
    <div class="hs-actions">
      <button class="hs-btn wide" @click="finish">Open {{ name.trim() || 'Home' }}</button>
    </div>
  </main>
</template>
