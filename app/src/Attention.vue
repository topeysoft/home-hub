<script setup lang="ts">
/*
 * The band: what Home owes a person, whatever layout they have chosen, as one
 * strip of chips. The command box sits above it, and everything else here is a
 * single line saying what wants them.
 *
 * It lives in one component rather than in each layout because two of these
 * lines are the ONLY route to something: a phone asking to be let in is the
 * only way a new phone joins a house it was not already in, and Needs a look
 * carries the only Sign in again there is for an expired account -- without it
 * the way back is Home Assistant's own UI, which is the thing this panel exists
 * not to need. A layout that forgot to copy them would strand somebody, so
 * there is nothing to copy. See layout.ts.
 *
 * Neither of those two is answered HERE any more, and that is the change worth
 * knowing about. A phone at the door is a pane that opens itself (AskPane.vue);
 * what has stopped answering is a page of This house (NotesPage.vue). What is
 * left in the band is one chip each, so nothing in it is ever taller than a
 * line of house news -- which is what lets a layout give the band a fixed
 * height and stop the row moving when something wants you.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { installUpdate, loadHealth, store } from './store'
import Icon from './Icon.vue'
import Say from './Say.vue'
import Asks from './Asks.vue'
import PhoneSteps from './PhoneSteps.vue'

/* say: whether the command box is drawn here. With the tabs across the top it
   lives in the bar along the bottom instead (see App.vue) -- still on Home, still
   on every layout, just not twice. */
withDefaults(defineProps<{ say?: boolean }>(), { say: true })

/* an update, offered once it exists and installed with one tap; the host does the work */
const update = computed(() => store.status?.update ?? null)
const updateReady = computed(() => !!update.value?.available && update.value?.state?.state !== 'running' && !update.value?.requested && !store.updating)
const updateBusy = computed(() => store.updating || !!update.value?.requested || update.value?.state?.state === 'running')

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
  <Say v-if="say" />

  <!-- One row for the nudges: a column under the side list, a strip of chips under the tabs. A
       phone at the door is first in it and wears the attention colour, but it is a chip like the
       rest -- the deciding is a pane that opens itself (AskPane.vue), so nothing in this band is
       ever taller than one line of house news. That is what lets a layout give the band a fixed
       height and stop the row moving when something wants you. -->
  <div class="nudges">
  <Asks />
  <button class="nudge" v-if="updateReady" @click="installUpdate">
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
  <!-- What has stopped answering, as one line. The list it opens is a page of This house
       (NotesPage.vue), because it is not news, it is a job with a button on it, and a house with
       three faults was spending a third of Home on saying so. -->
  <button class="nudge" v-if="store.notes.length" @click="store.sheet = 'notes'">
    <span class="nudge-icon"><Icon name="switch" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ store.notes.length === 1 ? 'Something needs a look' : `${store.notes.length} things need a look` }}</span><span class="nudge-sub">{{ store.notes[0].text }}</span></span>
  </button>
  </div>
  <div class="phone-card" v-if="phoneSteps">
    <PhoneSteps />
    <button class="button small ghost" @click="dismissPhone">Done, don't show this again</button>
  </div>

</template>
