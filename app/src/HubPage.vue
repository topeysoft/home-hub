<script setup lang="ts">
import { computed, ref } from 'vue'
import { store, notify } from './store'
import { downloadBackup, requestUpdate } from './api'
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
const when = (ts?: number | null) => ts ? new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : ''
</script>

<template>
  <div class="page">
    <p class="page-lede">The little computer running the house. It looks after itself; this is where you check on it.</p>

    <ul class="hub-rows">
      <li>
        <span class="hub-k">Software</span>
        <span class="hub-v">{{ !store.status?.version || store.status.version === 'dev' ? 'Development build' : store.status.version }}<span class="hub-sub" v-if="refused"> · {{ refused }} couldn’t be checked, so it wasn’t installed</span><span class="hub-sub" v-else-if="rolledBack"> · {{ rolledBack }} didn’t start, so this one was put back</span><span class="hub-sub" v-else-if="update?.checked"> · checked {{ when(update.checked) }}</span></span>
        <button class="button small" v-if="update?.available && !refused && !store.updating && !update.requested" @click="install">{{ rolledBack ? 'Try again' : 'Install the update' }}</button>
        <span class="hub-sub" v-else-if="store.updating || update?.requested || update?.state?.state === 'running'">Updating…</span>
        <span class="hub-sub" v-else-if="update?.available === false">Up to date</span>
        <span class="hub-sub" v-else-if="update?.error">Couldn't check: no internet?</span>
        <span v-else></span>
      </li>
      <li>
        <span class="hub-k">Backup</span>
        <span class="hub-v">Settings, rooms, routines, the engine's setup and the radios' keys, in one file.<span class="hub-sub"> It holds the house's keys: keep it private.</span></span>
        <button class="button small" :class="{ busy }" @click="backup">{{ busy ? 'Packing…' : 'Back up' }}</button>
      </li>
      <li>
        <span class="hub-k">Restore</span>
        <span class="hub-v">Put a backup back, here or on a new hub. Everything running now is replaced by what is in the file.</span>
        <Restore small />
      </li>
    </ul>
    <AdvancedLink />
  </div>
</template>
