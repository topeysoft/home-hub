<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { setupOwner, setupLogin, setupDone, addRoom, setPin, getAddress, type AddressState } from './api'
import { offersOutside } from './address'
import { remember } from './code'
import { store, load } from './store'
import Icon from './Icon.vue'
import LocationPicker from './LocationPicker.vue'
import Adding from './Adding.vue'
import Drivers from './Drivers.vue'
import Restore from './Restore.vue'
import PhoneSteps from './PhoneSteps.vue'
import AddressStep from './AddressStep.vue'

/* First run. One question per screen, in this order: who you are, where home is, which rooms,
   what to add. Every step after the first can be skipped and finished later from Home -- except the
   code, which cannot, because a house that is still open to the whole Wi-Fi is not set up yet.
   And one more after what to add, only when the address service is offering it: whether the house
   wants an address of its own for reaching it from outside (AddressStep.vue, design/address/). */
type Page = 'welcome' | 'login' | 'owner' | 'starting' | 'code' | 'location' | 'rooms' | 'devices' | 'address' | 'done'
const PAGES: Page[] = ['welcome', 'login', 'owner', 'starting', 'code', 'location', 'rooms', 'devices', 'address', 'done']
const preview = new URLSearchParams(location.search).get('page') as Page | null   // ?setup=1&page=rooms previews one screen
const page = ref<Page>(preview && PAGES.includes(preview) ? preview : 'welcome')
const status = computed(() => store.status)
const driver = computed(() => status.value?.driver ?? 'down')
const engineReady = computed(() => ['fresh', 'needs-login', 'connecting', 'ready'].includes(driver.value))
const busy = ref(false), error = ref(''), fromBackup = ref(false)
/* Something is being added right now: this step gets out of its way, the same as the Add page does.
   One surface per conversation, and Continue is not a thing to offer mid-question. */
const adding = ref(false)
const name = ref(''), home = ref(''), username = ref(''), password = ref('')
const advanced = `${location.protocol}//${location.hostname}:8123/`
/* Asked for once, at the start: whether the last step is offered at all. A hub that cannot reach the
   service, or a brain that predates it, simply never shows the step -- the house is complete without it. */
const address = ref<AddressState | null>(null)
getAddress().then(a => (address.value = a)).catch(() => {})

function next(after: Page) {
  const s = status.value
  if (after === 'welcome') {
    if (driver.value === 'fresh') return (page.value = 'owner')
    if (driver.value === 'needs-login') return (page.value = 'login')
    return (page.value = s?.owner ? (s.locked ? 'location' : 'code') : 'owner')
  }
  if (after === 'login') return (page.value = 'owner')
  if (after === 'owner') return (page.value = driver.value === 'ready' ? 'code' : 'starting')
  if (after === 'starting') return (page.value = s?.owner ? 'code' : 'owner')
  if (after === 'code') return (page.value = 'location')
  if (after === 'location') return (page.value = 'rooms')
  if (after === 'rooms') return (page.value = 'devices')
  if (after === 'devices') return (page.value = offersOutside(address.value) ? 'address' : 'done')
}
watch(driver, d => { if (d === 'ready' && page.value === 'starting') next('starting') })
watch(() => store.status?.owner, o => { if (o && !name.value) name.value = o })
watch(() => store.homeName, h => { if (h && !home.value) home.value = h }, { immediate: true })

async function saveOwner() {
  if (!name.value.trim()) { error.value = 'What should the house call you?'; return }
  busy.value = true; error.value = ''
  try { store.status = await setupOwner(name.value.trim(), home.value.trim() || `${name.value.trim().split(' ')[0]}'s house`); store.homeName = home.value; next('owner') }
  catch (e: any) { error.value = e.message }
  busy.value = false
}
async function signIn() {
  busy.value = true; error.value = ''
  try { store.status = await setupLogin(username.value.trim(), password.value); next('login') }
  catch (e: any) { error.value = e.message }
  busy.value = false
}

/* rooms: a few suggestions, plus your own */
const SUGGESTED = ['Living room', 'Kitchen', 'Bedroom', 'Bathroom', 'Office', 'Kids\' room', 'Garage', 'Hallway', 'Dining room', 'Basement', 'Porch', 'Backyard']
const existing = computed(() => store.rooms.filter(r => r.id !== 'unassigned').map(r => r.name))
const chosen = ref(new Set<string>())
const custom = ref('')
const isExisting = (n: string) => existing.value.some(e => e.toLowerCase() === n.toLowerCase())
const toggle = (n: string) => { if (isExisting(n)) return; chosen.value.has(n) ? chosen.value.delete(n) : chosen.value.add(n); chosen.value = new Set(chosen.value) }
function addCustom() { const n = custom.value.trim(); if (n && !isExisting(n)) chosen.value = new Set([...chosen.value, n]); custom.value = '' }
const allRooms = computed(() => [...SUGGESTED.filter(s => !isExisting(s)), ...[...chosen.value].filter(c => !SUGGESTED.includes(c))])
async function saveRooms() {
  busy.value = true; error.value = ''
  try { for (const n of chosen.value) await addRoom(n); chosen.value = new Set(); next('rooms') }
  catch (e: any) { error.value = e.message }
  busy.value = false
}

async function finish() {
  busy.value = true; error.value = ''
  try {
    store.status = await setupDone()
    if (location.search) history.replaceState(null, '', location.pathname)   // drop ?setup=1&page=… so the house shows
    store.previewSetup = false
    await load()
  } catch (e: any) { error.value = `Couldn't finish: ${e.message}` }
  busy.value = false
}
const firstRoom = computed(() => (store.rooms.find(r => r.id !== 'unassigned' && r.devices.some(d => d.capability === 'light')) ?? store.rooms.find(r => r.id !== 'unassigned'))?.name ?? 'Kitchen')
const firstName = computed(() => (status.value?.owner || name.value || '').split(' ')[0])
const readyLine = computed(() => {   // "Robin's house is ready." or "Home is ready, Robin."; never the name twice
  const h = store.homeName || 'Home', f = firstName.value
  return f && !h.toLowerCase().includes(f.toLowerCase()) ? `${h} is ready, ${f}.` : `${h} is ready.`
})
/* The numbered part of first run: every screen that asks something, in order. It used to
   count only the last four, so a person typed their name, chose a passcode, and was then told
   they were on "Step 1 of 4" -- two answers in and apparently at the beginning. */
const ASKED: Page[] = ['owner', 'code', 'location', 'rooms', 'devices']
const idx = computed(() => ASKED.indexOf(page.value))
const step = computed(() => (idx.value < 0 ? '' : `Step ${idx.value + 1} of ${ASKED.length}`))

/* Whether this step is taller than the panel it is on. The action row docks to the
   bottom when it is, so Continue is never a thing you have to find by scrolling a
   screen that gives no sign there is more of it. Measured rather than assumed from
   the width: the same step is short on a tall tablet and long on a 1280x800 wall. */
const scroller = ref<HTMLElement | null>(null)
const docked = ref(false)
function measure() {
  const el = scroller.value
  docked.value = !!el && el.scrollHeight - el.clientHeight > 1
}
let ro: ResizeObserver | undefined
onMounted(() => {
  measure()
  ro = new ResizeObserver(measure)
  if (scroller.value) ro.observe(scroller.value)
  window.addEventListener('resize', measure)
})
onUnmounted(() => { ro?.disconnect(); window.removeEventListener('resize', measure) })
/* A step change swaps the whole page under the transition, so re-measure once it has
   landed -- and again when what is on it grows, which `Adding` does as it goes. */
watch([page, adding, () => store.found.length], () => nextTick(measure))

/* the passcode on the settings */
const pin = ref(''), again = ref('')
async function saveCode() {
  error.value = ''
  if (!/^\d{4,8}$/.test(pin.value)) { error.value = 'A passcode is 4 to 8 digits.'; return }
  if (pin.value !== again.value) { error.value = 'The two do not match.'; return }
  busy.value = true
  try { store.status = await setPin(pin.value); remember(pin.value); next('code') } catch (e: any) { error.value = e.message }
  busy.value = false
}
</script>

<template>
  <main class="setup" :class="{ docked }" ref="scroller">
    <Transition name="view" mode="out-in" @after-enter="measure">
      <!-- welcome -->
      <section class="setup-page" v-if="page === 'welcome'" key="welcome">
        <span class="setup-mark"><Icon name="home" :size="30" /></span>
        <h1 class="display">Welcome home.</h1>
        <!-- No count in here, on purpose. It used to promise "one or two questions" and then ask
             five, and a sentence that has to be rewritten every time ASKED grows or shrinks is a
             sentence that will quietly go out of date. First run says as little as it can
             (design/words-setup/, B): one sentence a screen, and nothing the screen already shows. -->
        <p class="setup-lede">Run the whole house from this screen. Setting it up takes a few minutes.</p>
        <div class="setup-actions">
          <button class="button big" :disabled="!engineReady" @click="next('welcome')">Get started</button>
        </div>
        <p class="setup-status" v-if="store.restoring"><span class="pulse-dot"></span> Restoring your backup. The hub restarts, and this screen comes back with your house on it.</p>
        <p class="setup-status" v-else-if="!engineReady"><span class="pulse-dot"></span> Getting things ready. The first start takes a minute or two.</p>
        <p class="setup-status" v-else-if="driver === 'needs-login'">This hub was set up before. You’ll sign in with the name and password chosen then.</p>
        <p class="setup-foot">Moving from another hub? <button class="linkish" @click="fromBackup = !fromBackup">Bring its backup over</button></p>
        <Restore v-if="fromBackup" />
      </section>

      <!-- sign in to an engine someone already set up -->
      <section class="setup-page" v-else-if="page === 'login'" key="login">
        <h1 class="display">Sign in.</h1>
        <p class="setup-lede">Use the name and password this hub was set up with.</p>
        <label class="field"><span class="field-label">Name</span><input class="input" v-model="username" autocomplete="username" autocapitalize="off" spellcheck="false" @keydown.enter="signIn" /></label>
        <label class="field"><span class="field-label">Password</span><input class="input" type="password" v-model="password" autocomplete="current-password" @keydown.enter="signIn" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="signIn">Continue</button></div>
        <p class="setup-foot">Forgotten it? <a :href="advanced" target="_blank" rel="noopener">Reset it in Advanced</a>.</p>
      </section>

      <!-- who you are -->
      <section class="setup-page" v-else-if="page === 'owner'" key="owner">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">First, a couple of names.</h1>
        <p class="setup-lede">Yours, so the house can greet you, and one for the house itself.</p>
        <label class="field"><span class="field-label">Your name</span><input class="input" v-model="name" autocomplete="given-name" autocapitalize="words" placeholder="Robin" @keydown.enter="saveOwner" /></label>
        <label class="field"><span class="field-label">A name for the house</span><input class="input" v-model="home" autocapitalize="words" :placeholder="name.trim() ? `${name.trim().split(' ')[0]}'s house` : 'Home'" @keydown.enter="saveOwner" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="saveOwner">Continue</button></div>
      </section>

      <!-- waiting for the engine after creating the owner -->
      <section class="setup-page centered" v-else-if="page === 'starting'" key="starting">
        <span class="setup-mark pulse"><Icon name="home" :size="30" /></span>
        <h1 class="display">Setting up the house…</h1>
        <p class="setup-lede">{{ status?.reason || 'Just a moment.' }}</p>
      </section>

      <!-- the passcode -->
      <section class="setup-page" v-else-if="page === 'code'" key="code">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">Choose a passcode.</h1>
        <p class="setup-lede">You’ll need it to change the house: add phones or devices, rename rooms. Using the house doesn’t need it.</p>
        <p class="setup-note"><Icon name="lock" :size="16" /><span>Until it’s set, anyone on your Wi‑Fi can change the house.</span></p>
        <label class="field"><span class="field-label">Passcode, 4 to 8 digits</span><input class="input code-input" v-model="pin" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="saveCode" /></label>
        <label class="field"><span class="field-label">Type it again</span><input class="input code-input" v-model="again" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="saveCode" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions">
          <button class="button big" :class="{ busy }" @click="saveCode">Continue</button>
        </div>
      </section>

      <!-- where -->
      <section class="setup-page" v-else-if="page === 'location'" key="location">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">Where is home?</h1>
        <p class="setup-lede">Sunrise, sunset and the weather follow it, and it never leaves the hub.</p>
        <LocationPicker @saved="next('location')" />
        <div class="setup-actions">
          <button v-if="status?.location" class="button big" @click="next('location')">Continue</button>
          <button v-else class="button ghost" @click="next('location')">Skip for now</button>
        </div>
      </section>

      <!-- rooms -->
      <section class="setup-page" v-else-if="page === 'rooms'" key="rooms">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">Which rooms do you have?</h1>
        <p class="setup-lede">Tap the ones you have. You can change them any time.</p>
        <p class="setup-note plain" v-if="existing.length">The outlined ones are already in the house.</p>
        <div class="chips">
          <button v-for="r in existing" :key="'e' + r" class="chip-btn on fixed"><Icon name="check" :size="14" />{{ r }}</button>
          <button v-for="r in allRooms" :key="r" class="chip-btn" :class="{ on: chosen.has(r) }" @click="toggle(r)"><Icon v-if="chosen.has(r)" name="check" :size="14" />{{ r }}</button>
        </div>
        <label class="search"><Icon name="plus" :size="18" /><input v-model="custom" placeholder="Another room…" @keydown.enter="addCustom" autocapitalize="words" /><button class="button small" v-if="custom.trim()" @click="addCustom">Add</button></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions">
          <button class="button big" :class="{ busy }" @click="saveRooms">Continue</button>
        </div>
      </section>

      <!-- devices -->
      <section class="setup-page" v-else-if="page === 'devices'" key="devices">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">What's in the house?</h1>
        <p class="setup-lede">Things on your Wi‑Fi show up by themselves. Add some now, or later.</p>
        <Adding @busy="adding = $event" />
        <!-- the machinery is on This hub; first run shows a row only when it needs the person, and before the way on
             rather than under it, where a docked action row's ground would cover it (design/words-setup/, B) -->
        <div class="add-block setup-behind" v-if="!adding"><Drivers needs-you /></div>
        <div class="setup-actions" v-if="!adding"><button class="button big" @click="next('devices')">{{ status?.devices ? 'Continue' : 'Skip for now' }}</button></div>
      </section>

      <!-- the house's web address: optional, and only when the address service is offering it -->
      <AddressStep v-else-if="page === 'address' && address" :state="address" key="address" @done="page = 'done'" />

      <!-- done -->
      <section class="setup-page" v-else-if="page === 'done'" key="done">
        <span class="setup-mark done"><Icon name="check" :size="30" /></span>
        <h1 class="display">{{ readyLine }}</h1>
        <p class="setup-lede">Leave this screen up. It dims after a few minutes; touch it to wake it.</p>
        <PhoneSteps compact />
        <ul class="tips">
          <li><span class="tip-icon"><Icon name="sparkle" :size="18" /></span><span>Try it: type <b>“{{ firstRoom }} lights off”</b> into <b>Tell the house…</b> at the top of the screen.</span></li>
        </ul>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="finish">Start using the house</button></div>
      </section>
    </Transition>
  </main>
</template>
