<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { store, notify, installUpdate, restartHub } from './store'
import { askRestart, askUpdate, checkForUpdate, downloadBackup, getUpdateNotes, markNotesRead, setAutoUpdate, type RestartAsk, type Rung, type UpdateAsk, type UpdateNotes } from './api'
import Restore from './Restore.vue'
import AdvancedLink from './AdvancedLink.vue'

/* This hub: which build it is, whether a newer one exists, a backup to take away and a way to put one back.
   The phones that belong to the house are on the People page: they are about who, not about this computer. */
const update = computed(() => store.status?.update ?? null)
const busy = ref(false)
async function backup() {
  if (busy.value) return
  busy.value = true
  try { await downloadBackup(); notify('Your backup is on its way. Keep it somewhere safe; it holds the house’s keys.') }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = false
}
/* Installing, and the question in front of it.
 *
 * The same shape as the restart below, and deliberately so: an update is a restart with a download
 * in front of it, and half the sheet is the same brain's answer to the same question. What it adds
 * is the half a restart has no use for -- why this update exists, in the release's own words, and
 * the fact that the download is not a blackout. Home keeps its one-tap nudge; this is the page
 * somebody came to in order to find out more, so this is where the more lives.
 */
const uask = ref<UpdateAsk | null>(null)
const installBusy = ref(false)
async function openInstall() {
  try { uask.value = await askUpdate() } catch (e: any) { notify(e.message, 'error') }
}
async function goInstall() {
  if (installBusy.value) return
  installBusy.value = true
  /* Nothing is closed until the hub has taken it: a refusal -- a restore that started a second ago,
     a release pulled since this page loaded -- leaves the question up with the reason under it. */
  if (await installUpdate()) uask.value = null
  else await openInstall()
  installBusy.value = false
}
/* Where the host has got to. The brain is up for nearly all of an update, so this is a real answer
   for most of the wait rather than three dots. */
const phase = computed(() => update.value?.progress ?? null)
const busyUpdating = computed(() => !!store.updating || !!update.value?.requested || update.value?.state?.state === 'running')
/* A version that was installed, would not start, and was put back by the host (docs/updates.md,
   piece 1). Home stops nudging for it; here it is still one tap, because this page is where a person
   is the one choosing, and trying it a second time is often what fixes it. */
const rolledBack = computed(() => update.value?.state?.state === 'reverted' ? (update.value?.state?.bad || update.value?.rejected || 'That update') : '')
/* A release the hub would not vouch for: no signed record of what it is, or one signed by a key this
   hub does not know (docs/updates.md, piece 2). Nothing was installed and nothing is broken, and no
   button appears -- the same tap would refuse the same release, and this one is not the household's
   to fix. */
const refused = computed(() => update.value?.state?.state === 'refused' ? (update.value?.state?.bad || 'That update') : '')
/* The people who make the hub have pulled this release since signing it (docs/updates.md, piece 5).
   No button, and not because this hub failed at anything: it is the one case where somebody tapping
   Install would be overruled on purpose, and saying so is better than a tap that goes nowhere. */
const held = computed(() => !!update.value?.held)
/* Installing in the night without being asked. On by default where the hub can check what it is
   installing, because the alternative is what actually happens otherwise: nobody walks to the wall,
   and the house sits a year behind on the release that had the bug. A hub that cannot check waits
   to be asked, and says so here rather than leaving a switch that means something different. */
const autoBusy = ref(false)
async function flipAuto() {
  if (autoBusy.value) return
  autoBusy.value = true
  try { await setAutoUpdate(!update.value?.auto) }
  catch (e: any) { notify(e.message, 'error') }
  autoBusy.value = false
}
/* What changed. Opening this page is what marks the morning-after card read: nothing vanishes under
   a tap on Home, and somebody who came here to look has, by definition, looked. */
const notes = ref<UpdateNotes | null>(null)
const earlier = ref(false)
const earlierReleases = computed(() => (notes.value?.history ?? []).filter(r => r.version !== notes.value?.notes?.version && r.what.length))
onMounted(async () => {
  try { notes.value = await getUpdateNotes() } catch { /* an older hub, or no notes in this build */ }
  if (store.status?.update?.whats_new) { try { await markNotesRead() } catch { /* it will come back tomorrow */ } }
  /* Opening this page is also the check for an update: no button to explain, "checked just now" under
     the version is the answer, and Install appears by itself if there is one. Last, because it can
     take the brain a few seconds to hear back, and the notes should not wait on it. */
  try { const u = await checkForUpdate(); if (store.status) store.status.update = u } catch { /* offline, or an older hub: the row already says so */ }
})
/* Turning it off and on again.
 *
 * One button and no rung picker. A person at the wall cannot tell "restart the brain" from "restart
 * the machine" -- that is the whole reason they are at the wall -- so the hub picks the smallest
 * rung that could help and the next one up appears only once this one has visibly stopped helping.
 *
 * The first tap asks the hub what it would cost and turns the button into the question, the way
 * Needs a look does: every word of it is the brain's, because what stops, what keeps working and how
 * long it takes are facts about THIS house that a panel would only be guessing at. docs/restart.md.
 */
const ask = ref<RestartAsk | null>(null)
const rung = ref<Rung>('hub')
const restartBusy = ref(false)
async function openRestart(which: Rung = 'hub') {
  rung.value = which
  try { ask.value = await askRestart(which) } catch (e: any) { notify(e.message, 'error') }
}
async function goRestart(understood = false) {
  if (restartBusy.value) return
  restartBusy.value = true
  /* Nothing is closed until the hub has taken it: a refusal (an update started a second ago, or this
     phone may not) leaves the question on the screen with the reason under it. */
  if (await restartHub(rung.value, understood)) ask.value = null
  else await openRestart(rung.value)
  restartBusy.value = false
}
const when = (ts?: number | null) => ts ? new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : ''
</script>

<template>
  <div class="page">
    <p class="page-lede">The little computer running the house. It looks after itself; this is where you check on it.</p>

    <ul class="hub-rows">
      <li :class="{ asking: !!uask }">
        <span class="hub-k">Software</span>
        <template v-if="uask">
          <span class="hub-v">
            <b>{{ uask.title }}</b>
            <!-- Why this one, in the release's own words. The wait is the one moment somebody is
                 both captive and curious, and these were fetched and drawn nowhere until now. One
                 line, like the What's new row: split into a list they stop reading as the reason and
                 start reading as another column of costs. -->
            <span class="hub-sub line" v-if="uask.what.length">{{ uask.what.join(' ') }}</span>
            <span class="hub-sub line">{{ uask.keeps }} It takes {{ uask.how_long }}, and the screen is away for {{ uask.dark_how_long }} of that.</span>
            <span class="hub-sub line" v-for="(l, i) in uask.stops" :key="'s' + i">{{ l }}</span>
            <span class="hub-sub line warn" v-for="(l, i) in uask.flight" :key="'f' + i">{{ l }}</span>
            <span class="hub-sub line warn" v-if="uask.warn">{{ uask.warn }}</span>
            <span class="hub-sub line warn" v-if="uask.blocked">{{ uask.blocked }}</span>
          </span>
          <span class="note-ask">
            <button class="button small" v-if="!uask.blocked" :class="{ busy: installBusy }" @click="goInstall">{{ uask.yes }}</button>
            <button class="button small ghost" @click="uask = null">Not now</button>
          </span>
        </template>
        <template v-else>
        <span class="hub-v">{{ !store.status?.version || store.status.version === 'dev' ? 'Development build' : store.status.version }}<span class="hub-sub" v-if="held"> · {{ update?.latest?.version }} was paused by the people who make the hub</span><span class="hub-sub" v-else-if="refused"> · {{ refused }} couldn’t be checked, so it wasn’t installed</span><span class="hub-sub" v-else-if="rolledBack"> · {{ rolledBack }} didn’t start, so this one was put back</span><span class="hub-sub" v-else-if="update?.checked"> · checked {{ when(update.checked) }}</span>
          <!-- What the hub is doing right now, said in its own words rather than three dots. It is a
               line here and not a screen over the panel because the house still works: for all of
               this but the last stretch the brain is up and every light still answers. -->
          <span class="hub-sub line" v-if="busyUpdating">{{ phase?.says || 'Starting.' }} {{ (phase?.notices ?? []).join(' ') }}</span></span>
        <button class="button small" v-if="update?.available && !refused && !held && !busyUpdating" @click="openInstall">{{ rolledBack ? 'Try again' : 'Install the update' }}</button>
        <span class="hub-sub" v-else-if="busyUpdating">{{ phase?.step ? `Step ${phase.step} of ${phase.steps}` : 'Updating…' }}</span>
        <span class="hub-sub" v-else-if="update?.available === false">Up to date</span>
        <span class="hub-sub" v-else-if="update?.error">Couldn't check: no internet?</span>
        <span v-else></span>
        </template>
      </li>
      <li v-if="notes?.notes?.what?.length || earlierReleases.length">
        <span class="hub-k">What's new</span>
        <span class="hub-v">{{ notes?.notes?.what?.length ? notes.notes.what.join(' ') : 'Nothing was written down for this build.' }}
          <template v-if="earlier">
            <span class="was" v-for="r in earlierReleases" :key="r.version"><b>{{ r.version }}</b> {{ r.what.join(' ') }}</span>
          </template>
        </span>
        <button class="button small" v-if="earlierReleases.length" @click="earlier = !earlier">{{ earlier ? 'Hide' : 'Earlier' }}</button>
        <span v-else></span>
      </li>
      <li>
        <span class="hub-k">Updates</span>
        <span class="hub-v">{{ update?.auto ? 'Installed overnight, on their own.' : 'Installed when you tap, and not before.' }}<span class="hub-sub line">{{ update?.verified ? 'Only ones this hub can check, and it puts back any that won’t start.' : 'This hub can’t check an update yet, so it waits to be asked.' }}</span></span>
        <button class="toggle" role="switch" :aria-checked="!!update?.auto" aria-label="Install updates overnight" :class="{ on: update?.auto, busy: autoBusy }" @click="flipAuto"><span class="knob"></span></button>
      </li>
      <li>
        <span class="hub-k">Backup</span>
        <span class="hub-v">Everything the house knows, in one file.<span class="hub-sub line">Settings, rooms, routines, the engine's setup and the radios' keys. It holds the house's keys, so keep the file private.</span></span>
        <button class="button small" :class="{ busy }" @click="backup">{{ busy ? 'Packing…' : 'Back up' }}</button>
      </li>
      <li>
        <span class="hub-k">Restore</span>
        <span class="hub-v">Put a backup back, here or on a new hub.<span class="hub-sub line">Everything running now is replaced by what is in the file.</span></span>
        <Restore small />
      </li>
      <li :class="{ asking: !!ask }">
        <span class="hub-k">Restart</span>
        <template v-if="!ask">
          <span class="hub-v">If something's stuck, turn the hub off and on again.<span class="hub-sub line">Lights and switches keep working. It takes under a minute and this screen comes back on its own.</span></span>
          <button class="button small" v-if="!store.restarting" @click="openRestart('hub')">Restart</button>
          <span class="hub-sub" v-else>Restarting…</span>
        </template>
        <template v-else>
          <span class="hub-v">
            <b>{{ ask.title }}</b>
            <!-- What is still true while it is away, first: it is the thing people are actually asking. -->
            <span class="hub-sub line">{{ ask.keeps }} The screen goes dark for {{ ask.how_long }}.</span>
            <span class="hub-sub line" v-for="(line, i) in ask.stops" :key="i">{{ line }}</span>
            <!-- Half-done things, named before they are lost. Nothing vanishes under a tap unsaid. -->
            <span class="hub-sub line warn" v-for="(line, i) in ask.flight" :key="'f' + i">{{ line }}</span>
            <span class="hub-sub line warn" v-if="ask.weary">{{ ask.weary }}</span>
            <span class="hub-sub line warn" v-if="ask.warn">{{ ask.warn }}</span>
            <span class="hub-sub line warn" v-if="ask.blocked">{{ ask.blocked }}</span>
            <span class="hub-sub line warn" v-else-if="!ask.may">Restarting the house is for the screens that keep it. Someone at the wall can do it.</span>
          </span>
          <span class="note-ask">
            <button class="button small" v-if="ask.may && !ask.blocked" :class="{ busy: restartBusy }" @click="goRestart(!!ask.warn)">{{ ask.yes }}</button>
            <!-- The next rung up, and only once the hub says this one has stopped being the answer.
                 A ladder drawn as a menu is the diagnosis handed back to the household. -->
            <button class="button small ghost" v-if="ask.harder" @click="openRestart(ask.harder)">Restart {{ ask.harder === 'machine' ? 'the little computer' : 'everything' }} instead</button>
            <button class="button small ghost" @click="ask = null">Not now</button>
          </span>
        </template>
      </li>
    </ul>

    <AdvancedLink />
  </div>
</template>

<style scoped>
/* The restart row while its question is up: the question needs the width, so the row gives up its
   three columns and stacks. `warn` is the attention color the rest of the panel already uses. */
.hub-rows li.asking { align-items: flex-start; }
.hub-sub.warn { color: var(--lamp); opacity: 0.95; }
/* One earlier release per line, quieter than the one this hub is on. Kept here rather than in
   panel.css: it is three declarations and only this page has them. */
.was { display: block; margin-top: 0.45em; font-size: 0.92em; opacity: 0.55; }
.was b { font-weight: 600; margin-right: 0.35em; }
</style>
