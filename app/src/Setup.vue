<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { setupOwner, setupLogin, setupDone, addRoom } from './api'
import { store, load } from './store'
import Icon from './Icon.vue'
import LocationPicker from './LocationPicker.vue'
import AddPanel from './AddPanel.vue'
import Drivers from './Drivers.vue'

/* First run. One question per screen, in this order: who you are, where home is, which rooms,
   what to add. Every step after the first can be skipped and finished later from Home. */
type Page = 'welcome' | 'login' | 'owner' | 'starting' | 'location' | 'rooms' | 'devices' | 'done'
const PAGES: Page[] = ['welcome', 'login', 'owner', 'starting', 'location', 'rooms', 'devices', 'done']
const preview = new URLSearchParams(location.search).get('page') as Page | null   // ?setup=1&page=rooms previews one screen
const page = ref<Page>(preview && PAGES.includes(preview) ? preview : 'welcome')
const status = computed(() => store.status)
const driver = computed(() => status.value?.driver ?? 'down')
const engineReady = computed(() => ['fresh', 'needs-login', 'connecting', 'ready'].includes(driver.value))
const busy = ref(false), error = ref('')
const name = ref(''), home = ref(''), username = ref(''), password = ref('')
const advanced = `${location.protocol}//${location.hostname}:8123/`

function next(after: Page) {
  const s = status.value
  if (after === 'welcome') {
    if (driver.value === 'fresh') return (page.value = 'owner')
    if (driver.value === 'needs-login') return (page.value = 'login')
    return (page.value = s?.owner ? 'location' : 'owner')
  }
  if (after === 'login') return (page.value = 'owner')
  if (after === 'owner') return (page.value = driver.value === 'ready' ? 'location' : 'starting')
  if (after === 'starting') return (page.value = s?.owner ? 'location' : 'owner')
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
const phoneUrl = computed(() => location.hostname.endsWith('.local') || /^\d+\.\d+\.\d+\.\d+$/.test(location.hostname) ? `${location.protocol}//${location.host}` : 'http://hub.local')
const firstName = computed(() => (status.value?.owner || name.value || '').split(' ')[0])
const idx = computed(() => ['owner', 'location', 'rooms', 'devices'].indexOf(page.value))
</script>

<template>
  <main class="setup">
    <Transition name="view" mode="out-in">
      <!-- welcome -->
      <section class="setup-page" v-if="page === 'welcome'" key="welcome">
        <span class="setup-mark"><Icon name="home" :size="30" /></span>
        <h1 class="display">Welcome home.</h1>
        <p class="setup-lede">This screen will run the house: lights, screens, doors, cameras, all in one calm place. Setting it up takes a few minutes and one or two questions.</p>
        <div class="setup-actions">
          <button class="button big" :disabled="!engineReady" @click="next('welcome')">Get started</button>
        </div>
        <p class="setup-status" v-if="!engineReady"><span class="pulse-dot"></span> Getting things ready. The first start takes a minute or two.</p>
        <p class="setup-status" v-else-if="driver === 'needs-login'">The engine behind this hub was set up separately. You will sign in to it next.</p>
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

      <!-- where -->
      <section class="setup-page" v-else-if="page === 'location'" key="location">
        <p class="setup-step">Step {{ idx + 1 }} of 4</p>
        <h1 class="display">Where is home?</h1>
        <p class="setup-lede">The sky behind this screen, sunrise, sunset and the weather all follow it. It stays on the hub and is never shared.</p>
        <LocationPicker @saved="next('location')" />
        <div class="setup-actions"><button class="button ghost" @click="next('location')">{{ status?.location ? 'Keep it' : 'Later' }}</button></div>
      </section>

      <!-- rooms -->
      <section class="setup-page" v-else-if="page === 'rooms'" key="rooms">
        <p class="setup-step">Step {{ idx + 1 }} of 4</p>
        <h1 class="display">Which rooms do you have?</h1>
        <p class="setup-lede">Tap the ones that apply. You can rename or add more any time.</p>
        <div class="chips">
          <button v-for="r in existing" :key="'e' + r" class="chip-btn on fixed"><Icon name="check" :size="14" />{{ r }}</button>
          <button v-for="r in allRooms" :key="r" class="chip-btn" :class="{ on: chosen.has(r) }" @click="toggle(r)"><Icon v-if="chosen.has(r)" name="check" :size="14" />{{ r }}</button>
        </div>
        <label class="search"><Icon name="search" :size="18" /><input v-model="custom" placeholder="Another room…" @keydown.enter="addCustom" autocapitalize="words" /><button class="button small" v-if="custom.trim()" @click="addCustom">Add</button></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions">
          <button class="button big" :class="{ busy }" @click="saveRooms">Continue</button>
        </div>
      </section>

      <!-- devices -->
      <section class="setup-page" v-else-if="page === 'devices'" key="devices">
        <p class="setup-step">Step {{ idx + 1 }} of 4</p>
        <h1 class="display">What's in the house?</h1>
        <p class="setup-lede">Things already on your Wi‑Fi show up here on their own. Add what you like now; the rest can wait.</p>
        <AddPanel />
        <div class="add-block">
          <h3 class="label">Behind the scenes</h3>
          <Drivers />
        </div>
        <div class="setup-actions"><button class="button big" @click="next('devices')">{{ status?.devices ? 'Continue' : 'Skip for now' }}</button></div>
      </section>

      <!-- done -->
      <section class="setup-page" v-else-if="page === 'done'" key="done">
        <span class="setup-mark done"><Icon name="check" :size="30" /></span>
        <h1 class="display">{{ store.homeName || 'Home' }} is ready{{ firstName ? `, ${firstName}` : '' }}.</h1>
        <p class="setup-lede">Leave this screen on the wall. It rests to a clock after a few minutes and wakes with a touch.</p>
        <ul class="tips">
          <li><span class="tip-icon"><Icon name="tv" :size="18" /></span><span>On a phone, open <b>{{ phoneUrl }}</b> on the home Wi‑Fi and choose <b>Add to Home Screen</b>. It becomes an app.</span></li>
          <li><span class="tip-icon"><Icon name="sparkle" :size="18" /></span><span>New things you plug in appear under <b>Found nearby</b> on the Home screen.</span></li>
          <li><span class="tip-icon"><Icon name="home" :size="18" /></span><span>Devices that don't know their room wait under <b>New devices</b> until you place them.</span></li>
        </ul>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="setup-actions"><button class="button big" :class="{ busy }" @click="finish">Open Home</button></div>
      </section>
    </Transition>
  </main>
</template>
