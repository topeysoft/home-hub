<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { store, notify } from './store'
import { checkForUpdate, downloadBackup, getUpdateNotes, markNotesRead, requestUpdate, setAutoUpdate, type UpdateNotes } from './api'
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
async function install() {
  try { await requestUpdate(); store.updating = true; notify('Updating. The lights keep working; this screen comes back on its own.') }
  catch (e: any) { notify(e.message, 'error') }
}
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
const when = (ts?: number | null) => ts ? new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : ''
</script>

<template>
  <div class="page">
    <p class="page-lede">The little computer running the house. It looks after itself; this is where you check on it.</p>

    <ul class="hub-rows">
      <li>
        <span class="hub-k">Software</span>
        <span class="hub-v">{{ !store.status?.version || store.status.version === 'dev' ? 'Development build' : store.status.version }}<span class="hub-sub" v-if="held"> · {{ update?.latest?.version }} was paused by the people who make the hub</span><span class="hub-sub" v-else-if="refused"> · {{ refused }} couldn’t be checked, so it wasn’t installed</span><span class="hub-sub" v-else-if="rolledBack"> · {{ rolledBack }} didn’t start, so this one was put back</span><span class="hub-sub" v-else-if="update?.checked"> · checked {{ when(update.checked) }}</span></span>
        <button class="button small" v-if="update?.available && !refused && !held && !store.updating && !update.requested" @click="install">{{ rolledBack ? 'Try again' : 'Install the update' }}</button>
        <span class="hub-sub" v-else-if="store.updating || update?.requested || update?.state?.state === 'running'">Updating…</span>
        <span class="hub-sub" v-else-if="update?.available === false">Up to date</span>
        <span class="hub-sub" v-else-if="update?.error">Couldn't check: no internet?</span>
        <span v-else></span>
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
    </ul>

    <AdvancedLink />
  </div>
</template>

<style scoped>
/* One earlier release per line, quieter than the one this hub is on. Kept here rather than in
   panel.css: it is three declarations and only this page has them. */
.was { display: block; margin-top: 0.45em; font-size: 0.92em; opacity: 0.55; }
.was b { font-weight: 600; margin-right: 0.35em; }
</style>
