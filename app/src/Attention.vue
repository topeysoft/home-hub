<script setup lang="ts">
/*
 * What Home owes a person, whatever layout they have chosen: the command box, a
 * phone asking to be let in, the nudges, and the things that need a look.
 *
 * It lives in one component rather than in each layout because two of these are
 * the ONLY route to something: <Asks /> is the only way to approve a new phone
 * (without it a house can only be joined from a phone already in it), and the
 * Sign in again in "Needs a look" is the only way to re-authenticate an expired
 * account without opening Home Assistant. A layout that forgot to copy them
 * would strand somebody, so there is nothing to copy. See layout.ts.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { loadHealth, notify, openFlow, store } from './store'
import { requestUpdate, retryEntry, type Note } from './api'
import Icon from './Icon.vue'
import Say from './Say.vue'
import Asks from './Asks.vue'
import PhoneSteps from './PhoneSteps.vue'

/* an update, offered once it exists and installed with one tap; the host does the work */
const update = computed(() => store.status?.update ?? null)
const updateReady = computed(() => !!update.value?.available && update.value?.state?.state !== 'running' && !update.value?.requested && !store.updating)
const updateBusy = computed(() => store.updating || !!update.value?.requested || update.value?.state?.state === 'running')
async function install() {
  try { await requestUpdate(); store.updating = true; notify('Updating. The lights keep working; this screen comes back on its own.') }
  catch (e: any) { notify(e.message, 'error') }
}
const noteIcon = (k: string) => k === 'offline' ? 'refresh' : k === 'storage' ? 'home' : k === 'driver' ? 'switch' : 'sparkle'
/* a line here is only worth reading if something can be done about it, so the ones that can carry the doing */
const retrying = ref('')
async function again(n: Note) {
  if (!n.retry || retrying.value) return
  retrying.value = n.retry
  try { store.status = await retryEntry(n.retry); await loadHealth(); notify('Asked it to try again.') }
  catch (e: any) { notify(e.message, 'error') }
  retrying.value = ''
}

/* on a phone that is still in a browser tab: offer the home-screen install once, with the steps for this phone */
const onPhone = matchMedia('(max-width: 860px)').matches
const standalone = matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true
function remembered(k: string) { try { return localStorage.getItem(k) } catch { return null } }
const phoneNudge = ref(onPhone && !standalone && remembered('phone-nudge') !== 'done')
const phoneSteps = ref(false)
function dismissPhone() { phoneNudge.value = false; phoneSteps.value = false; try { localStorage.setItem('phone-nudge', 'done') } catch {} }

let t3: number | undefined
onMounted(() => { loadHealth(); t3 = window.setInterval(loadHealth, 60000) })
onUnmounted(() => clearInterval(t3))

defineExpose({ updateReady })
</script>

<template>
  <Say />
  <Asks />

  <button class="nudge" v-if="updateReady" @click="install">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">An update is ready</span><span class="nudge-sub">{{ update?.latest?.title || 'New for the hub.' }} Tap to install; it takes a few minutes and the lights keep working.</span></span>
  </button>
  <div class="nudge quiet" v-else-if="updateBusy">
    <span class="nudge-icon pulse"><Icon name="refresh" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Updating the hub</span><span class="nudge-sub">This screen will blink and come back on its own. Nothing needs doing.</span></span>
  </div>
  <button class="nudge" v-if="store.found.length" @click="store.sheet = 'add'">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ store.found.length === 1 ? `Found ${store.found[0].title}` : `Found ${store.found.length} new things nearby` }}</span><span class="nudge-sub">{{ store.found.length === 1 ? 'Tap to add it to the house.' : store.found.slice(0, 3).map(f => f.title).join(', ') + (store.found.length > 3 ? '…' : '') }}</span></span>
  </button>
  <button class="nudge" v-if="store.status?.setup_done && store.status.locked === false" @click="store.sheet = 'code'">
    <span class="nudge-icon"><Icon name="lock" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Lock the settings</span><span class="nudge-sub">Anyone on the Wi‑Fi can change the house right now. A code keeps the controls open and the settings yours.</span></span>
  </button>
  <button class="nudge" v-if="store.ambientLoaded && !store.ambient.location" @click="store.sheet = 'location'">
    <span class="nudge-icon"><Icon name="pin" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Where is home?</span><span class="nudge-sub">Set a location once and the sky, sunrise and weather will follow it.</span></span>
  </button>
  <button class="nudge" v-if="phoneNudge && !phoneSteps" @click="phoneSteps = true">
    <span class="nudge-icon"><Icon name="phone" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Put the house on your home screen</span><span class="nudge-sub">One tap from your phone's first screen, full screen, no address to type.</span></span>
  </button>
  <div class="phone-card" v-if="phoneSteps">
    <PhoneSteps />
    <button class="button small ghost" @click="dismissPhone">Done, don't show this again</button>
  </div>

  <div class="block" v-if="store.notes.length">
    <h2 class="label">Needs a look</h2>
    <ul class="recent notes">
      <li v-for="(n, i) in store.notes" :key="i">
        <span class="recent-icon"><Icon :name="noteIcon(n.kind)" :size="16" /></span>
        <span class="recent-text">{{ n.text }}</span>
        <button v-if="n.flow" class="button small" @click="openFlow(n.flow)">{{ n.do || 'Sign in again' }}</button>
        <button v-else-if="n.retry" class="button small" :class="{ busy: retrying === n.retry }" :disabled="!!retrying" @click="again(n)">{{ n.do || 'Try again' }}</button>
        <button v-else-if="n.kind === 'update'" class="button small" @click="install">Try again</button>
        <span v-else></span>
      </li>
    </ul>
  </div>
</template>
