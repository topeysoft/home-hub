<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { setupOwner, setupLogin, setupDone, addRoom, setPin } from './api'
import { remember } from './code'
import { store, load } from './store'
import Icon from './Icon.vue'
import LocationPicker from './LocationPicker.vue'
import Adding from './Adding.vue'
import Drivers from './Drivers.vue'
import Restore from './Restore.vue'
import PhoneSteps from './PhoneSteps.vue'

/* First run. One question per screen, in this order: who you are, where home is, which rooms,
   what to add. Every step after the first can be skipped and finished later from Home -- except the
   code, which cannot, because a house that is still open to the whole Wi-Fi is not set up yet. */
type Page = 'welcome' | 'login' | 'owner' | 'starting' | 'code' | 'location' | 'rooms' | 'devices' | 'done'
const PAGES: Page[] = ['welcome', 'login', 'owner', 'starting', 'code', 'location', 'rooms', 'devices', 'done']
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
  if (after === 'devices') return (page.value = 'done')
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
const readyLine = computed(() => {   // "Nadine's house is ready." or "Home is ready, Nadine."; never the name twice
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
             sentence that will quietly go out of date. What the number was really doing was
             softening the ask; "you can change any of it later" does that instead, and stays true
             at any length -- every answer in first run is editable afterwards. -->
        <p class="setup-lede">This screen will run the house: lights, screens, doors, cameras, all in one calm place. Setting it up takes a few minutes, and you can change any of it later.</p>
        <div class="setup-actions">
          <button class="button big" :disabled="!engineReady" @click="next('welcome')">Get started</button>
        </div>
        <p class="setup-status" v-if="store.restoring"><span class="pulse-dot"></span> Restoring. The hub restarts and this screen comes back as your house.</p>
        <p class="setup-status" v-else-if="!engineReady"><span class="pulse-dot"></span> Getting things ready. The first start takes a minute or two.</p>
        <p class="setup-status" v-else-if="driver === 'needs-login'">The engine behind this hub was set up separately. You will sign in to it next.</p>
        <p class="setup-foot">Moving from another hub? <button class="linkish" @click="fromBackup = !fromBackup">Bring its backup over</button></p>
        <Restore v-if="fromBackup" />
      </section>

      <!-- sign in to an engine someone already set up -->
      <section class="setup-page" v-else-if="page === 'login'" key="login">
        <h1 class="display">Sign in.</h1>
        <p class="setup-lede">Home Assistant is already running here. Use the name and password that were set for it and this panel will take it from there.</p>
        <label class="field"><span class="field-label">Name</span><input class="input" v-model="username" autocomplete="username" autocapitalize="off" spellcheck="false" @keydown.enter="signIn" /></label>
        <label class="field"><span class="field-label">Password</span><input class="input" type="password" v-model="password" autocomplete="current-password" @keydown.enter="signIn" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="signIn">Continue</button></div>
        <p class="setup-foot">Stuck? <a :href="advanced" target="_blank" rel="noopener">Open Home Assistant</a> to reset the password.</p>
      </section>

      <!-- who you are -->
      <section class="setup-page" v-else-if="page === 'owner'" key="owner">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">First, a couple of names.</h1>
        <p class="setup-lede">Yours, so the house can greet you, and one for the house itself.</p>
        <label class="field"><span class="field-label">Your name</span><input class="input" v-model="name" autocomplete="given-name" autocapitalize="words" placeholder="Nadine" @keydown.enter="saveOwner" /></label>
        <label class="field"><span class="field-label">Call this home</span><input class="input" v-model="home" autocapitalize="words" :placeholder="name.trim() ? `${name.trim().split(' ')[0]}'s house` : 'Home'" @keydown.enter="saveOwner" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="saveOwner">Continue</button></div>
      </section>

      <!-- waiting for the engine after creating the owner -->
      <section class="setup-page centered" v-else-if="page === 'starting'" key="starting">
        <span class="setup-mark pulse"><Icon name="home" :size="30" /></span>
        <h1 class="display">Building your home…</h1>
        <p class="setup-lede">{{ status?.reason || 'Just a moment.' }}</p>
      </section>

      <!-- the passcode -->
      <section class="setup-page" v-else-if="page === 'code'" key="code">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">A passcode for changes.</h1>
        <p class="setup-lede">Four to eight digits. Anyone in the house can still work the lights from the wall without it — the passcode is for <em>changing</em> the house: adding devices, renaming rooms, taking a copy away with you.</p>
        <p class="setup-note"><Icon name="lock" :size="16" /><span>The one step that can't wait. Until it is set, anyone on your Wi‑Fi can change the house too.</span></p>
        <label class="field"><span class="field-label">Passcode</span><input class="input code-input" v-model="pin" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="saveCode" /></label>
        <label class="field"><span class="field-label">Once more</span><input class="input code-input" v-model="again" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="saveCode" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions">
          <button class="button big" :class="{ busy }" @click="saveCode">Continue</button>
        </div>
      </section>

      <!-- where -->
      <section class="setup-page" v-else-if="page === 'location'" key="location">
        <p class="setup-step">{{ step }}</p>
        <h1 class="display">Where is home?</h1>
        <p class="setup-lede">The sky behind this screen, sunrise, sunset and the weather all follow it. It stays on the hub and is never shared.</p>
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
        <p class="setup-lede">Tap the ones that apply. You can rename or add more any time.</p>
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
        <p class="setup-lede">Things already on your Wi‑Fi show up here on their own. Add what you like now; the rest can wait.</p>
        <Adding @busy="adding = $event" />
        <div class="setup-actions" v-if="!adding"><button class="button big" @click="next('devices')">{{ status?.devices ? 'Continue' : 'Skip for now' }}</button></div>
        <div class="add-block setup-behind" v-if="!adding">
          <h3 class="label">Behind the scenes</h3>
          <Drivers />
        </div>
      </section>

      <!-- done -->
      <section class="setup-page" v-else-if="page === 'done'" key="done">
        <span class="setup-mark done"><Icon name="check" :size="30" /></span>
        <h1 class="display">{{ readyLine }}</h1>
        <p class="setup-lede">Leave this screen on the wall. It rests to a clock after a few minutes and wakes with a touch.</p>
        <PhoneSteps compact />
        <ul class="tips">
          <li><span class="tip-icon"><Icon name="sparkle" :size="18" /></span><span>Tell the house what you want in the box at the top of Home: <b>“{{ firstRoom }} lights off”</b>, <b>“is the front door locked?”</b>.</span></li>
          <li><span class="tip-icon"><Icon name="sparkle" :size="18" /></span><span>New things you plug in appear under <b>Found nearby</b> on the Home screen.</span></li>
          <li><span class="tip-icon"><Icon name="home" :size="18" /></span><span>Devices that don't know their room wait under <b>New devices</b> until you place them.</span></li>
        </ul>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="finish">Open Home</button></div>
      </section>
    </Transition>
  </main>
</template>
