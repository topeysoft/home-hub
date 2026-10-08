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
import { deviceById, installUpdate, keptPrints, loadHealth, notify, perform, plainly, store } from './store'
import { bandNotes, printCards } from './printers'
import { chargerBand } from './chargers'
import { stripSecondLater } from './api'
import { controllerBand, type ControllerLine } from './controller'
import Icon from './Icon.vue'
import Say from './Say.vue'
import Asks from './Asks.vue'
import { type BandLine, stripWaiting, waitingBand } from './adding'
import { appHost, offerMove } from './move'
import { inApp } from './inapp'
import { narrow } from './band'

/* What the band says about things waiting to be set up, as one line: found on the network, still
   knocking over Bluetooth, or both. `tick` is here because the line folds with AGE and nothing else
   changes when it does -- without something moving, a knock would keep shouting until the next poll
   happened to land. Once a minute is as exact as an hour needs. */
/* The house has its own address and this phone is not in the Houses app yet (design/houses/, MoveToApp; before
   3 October, design/away/ NamedC-home): one line, on every phone of the house -- never the wall, which stays home,
   and never inside the app itself. */
const moveTo = computed(() => offerMove(store.me, inApp) ? appHost(store.me?.address) : '')
const tick = ref(Date.now())
let t4: number | undefined
const waiting = computed(() => waitingBand(store.found, store.strip, tick.value, store.printers?.found ?? []))
/* Needs a look, less what a card on this screen is already saying. The band sits over Home's row, and a
   printer waiting for a spool is its card there -- with the question and the two answers -- so a line
   above it saying the same thing is the sentence twice (design/printers/StatesB). printers.ts, bandNotes. */
const notes = computed(() => bandNotes(store.notes, printCards(store.printers?.printers ?? [], keptPrints()).map(p => p.id)))
const fromControllers = computed(() => controllerBand(store.strip, store.roofline, tick.value))
async function openController(l: ControllerLine) {
  try {
    if (l.strip) { store.strip = await stripSecondLater(l.strip); store.stripAsked = true }
    else if (l.roof) { const d = deviceById(l.roof); if (d) await perform(d, 'off', undefined, { state: 'off' }) }
  } catch (e: any) { notify(e.message, 'error') }
}
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

/* On a phone the band is sorted by kind (band.ts): what needs you keeps its line, news is one row of
   chips, and setup has gone to Finish setting up in This house. On a wall nothing here changes. A chip
   cannot carry "tap to install" and how long it takes, so on a phone the update opens The hub, where both
   are said beside the button, rather than installing from a three-word chip. */
const setupHere = computed(() => !narrow.value)
function openUpdate() { if (narrow.value) store.sheet = 'hub'; else installUpdate() }
const knock = computed(() => waiting.value.filter(w => w.id === 'knock'))
const found = computed(() => waiting.value.filter(w => w.id !== 'knock'))
/* rendered only with something in it, so an empty band still collapses (.nudges:not(:has(> *))) */
/* the car charging, as news (design/charger/, C's line): its card is in its room, so this is Home's only */
const charging = computed(() => chargerBand())
const news = computed(() => updateReady.value || !!whatsNew.value || !!moveTo.value || found.value.length > 0 || charging.value.length > 0)

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
  <div class="nudge quiet" v-if="!updateReady && updateBusy">
    <span class="nudge-icon pulse"><Icon name="refresh" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Updating the hub</span><span class="nudge-sub">{{ phase?.says || 'Starting.' }} {{ phase?.dark ? 'This screen will blink and come back.' : 'Lights and switches keep working.' }} {{ (phase?.notices ?? []).join(' ') }}</span></span>
  </div>
  <!-- SOMETHING NEW IS HERE, AND THIS IS THE ONLY WAY IT SAYS SO (design/knock/). A thing found on
       the network has always been one line here; a knock over Bluetooth used to take the whole
       screen instead, up to a hundred seconds after it was plugged in. It is this line now, and it
       is the same line: a knock shouts for an hour, then folds in with whatever else is waiting,
       because a line that will not go away is the interruption again, slower. Which of those it is
       is waitingBand() in adding.ts, pinned by a test. A knock is a line on a phone too; what it
       folds into is news, and goes in the row below. -->
  <button class="nudge" v-for="w in knock" :key="w.id" @click="openWaiting(w)">
    <span class="nudge-icon"><Icon name="light" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ w.title }}</span><span class="nudge-sub">{{ w.sub }}</span></span>
  </button>
  <!-- THE NEWS. On a wall these are chips in the band like the rest (the box is display: contents);
       on a phone they are one row of quiet chips under the lines that need you (design/band/,
       LineChipsBC), each still named, the row as tall as one chip however many there are. -->
  <div class="nudge-news" v-if="news">
  <button class="nudge" v-if="updateReady" @click="openUpdate">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">An update is ready</span><span class="nudge-sub">{{ update?.latest?.title || 'New for the hub.' }} Tap to install: {{ howLong }}, and the lights keep working throughout.</span></span>
  </button>
  <button class="nudge" v-if="whatsNew" @click="store.sheet = 'hub'">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">What's new</span><span class="nudge-sub">{{ whatsNew.what.join(' ') }}</span></span>
  </button>
  <button class="nudge" v-if="moveTo" @click="store.moving = true">
    <span class="nudge-icon"><Icon name="globe" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">A new link for the house</span><span class="nudge-sub">Switch this phone to {{ moveTo }}</span></span>
  </button>
  <button class="nudge" v-for="w in found" :key="w.id" @click="openWaiting(w)">
    <span class="nudge-icon"><Icon name="sparkle" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ w.title }}</span><span class="nudge-sub">{{ w.sub }}</span></span>
  </button>
  <button class="nudge charging" v-for="c in charging" :key="'charger:' + c.id" @click="store.opened = c.device">
    <span class="nudge-icon"><Icon name="charger" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ c.title }}</span><span class="nudge-sub">{{ c.sub }}</span></span>
  </button>
  </div>
  <button class="nudge" v-for="l in fromControllers" :key="l.id" @click="openController(l)">
    <span class="nudge-icon"><Icon name="light" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ l.title }}</span><span class="nudge-sub">{{ l.sub }}</span></span>
  </button>
  <!-- SOMEBODY IS TRYING A SIGNAL, and every wall says so -- not only the one they started it from --
       because "after dark" is set aside while they do, and a drive lighting up at lunch should not
       surprise whoever is in the kitchen. design/signal/Chosen.dc.html. -->
  <button class="nudge quiet" v-if="store.signalTry?.state === 'watching'" @click="store.sheet = 'signals'">
    <span class="nudge-icon pulse"><Icon name="light" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Trying “{{ store.signalTry.name }}”</span><span class="nudge-sub">The lights may show it in daylight for the next few minutes. Tap to see what the house has seen.</span></span>
  </button>
  <!-- SETUP. On a phone these three are Finish setting up in This house instead (band.ts). -->
  <button class="nudge" v-if="setupHere && store.status?.setup_done && store.status.locked === false" @click="store.sheet = 'code'">
    <span class="nudge-icon"><Icon name="lock" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Set a passcode</span><span class="nudge-sub">Anyone on your Wi‑Fi can change the house right now. A passcode keeps that to you; lights and scenes stay open to everyone.</span></span>
  </button>
  <button class="nudge" v-if="setupHere && store.ambientLoaded && !store.ambient.location" @click="store.sheet = 'location'">
    <span class="nudge-icon"><Icon name="pin" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">Where is home?</span><span class="nudge-sub">Set a location once and the sky, sunrise and weather will follow it.</span></span>
  </button>
  <!-- What has stopped answering, as one line. The list it opens is a page of This house
       (NotesPage.vue), because it is not news, it is a job with a button on it, and a house with
       three faults was spending a third of Home on saying so. -->
  <button class="nudge" v-if="notes.length" @click="store.sheet = 'notes'">
    <span class="nudge-icon"><Icon name="switch" :size="20" /></span>
    <span class="nudge-text"><span class="nudge-title">{{ notes.length === 1 ? 'Something needs a look' : `${notes.length} things need a look` }}</span><span class="nudge-sub">{{ notes[0].band || notes[0].text }}</span></span>
  </button>
  </div>

</template>
