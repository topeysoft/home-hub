<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
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
import { installUpdate, loadHealth, plainly, store } from './store'
import Icon from './Icon.vue'
import Say from './Say.vue'
import Asks from './Asks.vue'
import PhoneSteps from './PhoneSteps.vue'
import { type BandLine, stripWaiting, waitingBand } from './adding'

/* What the band says about things waiting to be set up, as one line: found on the network, still
   knocking over Bluetooth, or both. `tick` is here because the line folds with AGE and nothing else
   changes when it does -- without something moving, a knock would keep shouting until the next poll
   happened to land. Once a minute is as exact as an hour needs. */
const tick = ref(Date.now())
let t4: number | undefined
const waiting = computed(() => waitingBand(store.found, store.strip, tick.value))
/* Tapping a knock's own line is the asking that direction C is about: it opens the conversation,
   here, now. A folded line has stopped being about any one thing, so it opens Add and lets the row
   there be the choice -- which is what the found line has always done. */
function openWaiting(w: BandLine) {
  if (w.opens === 'strip' && stripWaiting(store.strip?.state)) { store.stripAsked = true; return }
  store.sheet = 'add'
}

/* say: whether the command box is drawn here. With the tabs across the top it
   lives in the bar along the bottom instead (see App.vue) -- still on Home, still
   on every layout, just not twice. */
withDefaults(defineProps<{ say?: boolean }>(), { say: true })

/* an update, offered once it exists and installed with one tap; the host does the work */
const update = computed(() => store.status?.update ?? null)
const updateReady = computed(() => !!update.value?.offer && update.value?.state?.state !== 'running' && !update.value?.requested && !store.updating)
const updateBusy = computed(() => store.updating || !!update.value?.requested || update.value?.state?.state === 'running')
/* Where the host has got to, in the brain's words. For most of an update the brain is up and can
   answer this, which is why the wait is a line here and not a wall across the panel: the house is
   working, and saying so is the difference between waiting and worrying. */
const phase = computed(() => update.value?.progress ?? null)
const howLong = computed(() => plainly(update.value?.seconds ?? 300))

/* What changed, the morning after the hub updated itself. Since piece 4 of docs/updates.md the
   ordinary way an update happens is overnight, so nobody is ever standing in front of a release note
   before it installs -- this is the only place the notes get read, and the card carries the words
   themselves rather than a link to them.

   Tapping opens This hub, where the notes live, and does not clear the card under the finger:
   opening that page is what marks them read. */
const whatsNew = computed(() => store.status?.update?.whats_new ?? null)

/* on a phone that is still in a browser tab: offer the home-screen install once, with the steps for this phone */
const onPhone = matchMedia('(max-width: 860px)').matches
const standalone = matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true
function remembered(k: string) { try { return localStorage.getItem(k) } catch { return null } }
const phoneNudge = ref(onPhone && !standalone && remembered('phone-nudge') !== 'done')
const phoneSteps = ref(false)
function dismissPhone() { phoneNudge.value = false; phoneSteps.value = false; try { localStorage.setItem('phone-nudge', 'done') } catch {} }

let t3: number | undefined
onMounted(() => {
  loadHealth(); t3 = window.setInterval(loadHealth, 60000)
  t4 = window.setInterval(() => { tick.value = Date.now() }, 60000)
})
onUnmounted(() => { clearInterval(t3); clearInterval(t4) })

defineExpose({ updateReady })
</script>

<template>
  <Say v-if="say" />

  <!-- One row for the nudges: a column under the side list, a strip of chips under the tabs. A
       phone at the door is first in it and wears the attention color, but it is a chip like the
       rest -- the deciding is a pane that opens itself (AskPane.vue), so nothing in this band is
       ever taller than one line of house news. That is what lets a layout give the band a fixed
       height and stop the row moving when something wants you. -->
  <div class="nudges">
  <Asks />
  <button class="nudge" v-if="updateReady" @click="installUpdate">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">An update is ready</span><span class="nudge-sub">{{ update?.latest?.title || 'New for the hub.' }} Tap to install: {{ howLong }}, and the lights keep working throughout.</span></span>
  </button>
  <div class="nudge quiet" v-else-if="updateBusy">
    <span class="nudge-icon pulse"><Icon name="refresh" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Updating the hub</span><span class="nudge-sub">{{ phase?.says || 'Starting.' }} {{ phase?.dark ? 'This screen will blink and come back.' : 'Everything keeps working while it does.' }} {{ (phase?.notices ?? []).join(' ') }}</span></span>
  </div>
  <button class="nudge" v-if="whatsNew" @click="store.sheet = 'hub'">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">What's new</span><span class="nudge-sub">{{ whatsNew.what.join(' ') }}</span></span>
  </button>
  <!-- SOMETHING NEW IS HERE, AND THIS IS THE ONLY WAY IT SAYS SO (design/knock/). A thing found on
       the network has always been one line here; a knock over Bluetooth used to take the whole
       screen instead, up to a hundred seconds after it was plugged in. It is this line now, and it
       is the same line: a knock shouts for an hour, then folds in with whatever else is waiting,
       because a line that will not go away is the interruption again, slower. Which of those it is
       is waitingBand() in adding.ts, pinned by a test. -->
  <button class="nudge" v-for="w in waiting" :key="w.id" @click="openWaiting(w)">
    <span class="nudge-icon"><Icon :name="w.id === 'knock' ? 'light' : 'sparkle'" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ w.title }}</span><span class="nudge-sub">{{ w.sub }}</span></span>
  </button>
  <button class="nudge" v-if="store.status?.setup_done && store.status.locked === false" @click="store.sheet = 'code'">
    <span class="nudge-icon"><Icon name="lock" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Lock the settings</span><span class="nudge-sub">Anyone on the Wi‑Fi can change the house right now. A passcode keeps the controls open and the settings yours.</span></span>
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
