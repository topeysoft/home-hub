<script setup lang="ts">
/*
 * Needs a look: the things the house cannot fix by itself.
 *
 * An account whose sign-in has expired, an integration that stopped answering,
 * an update that failed. layout.ts calls this a strand because it carries the
 * only Sign in again a person has -- without it an expired account can only be
 * put right by opening Home Assistant, which is the thing this panel exists not
 * to need.
 *
 * It used to be a list sitting under the nudges on Home, in every arrangement,
 * pushing whatever came after it down the screen. That is the wrong shape for
 * it twice over. It is not news, it is a job with a button on it, so it belongs
 * where the jobs are; and a house with three faults was spending a third of
 * Home on saying so. Now the band carries one chip and this is what the chip
 * opens -- a door in This house that only exists while there is something
 * behind it.
 *
 * Every line is the brain's own words. The panel does not translate them,
 * because it does not know what it is looking at; what it adds is the one
 * button that does something about it.
 */
import { ref } from 'vue'
import { installUpdate, loadHealth, notify, openFlow, store } from './store'
import { retryEntry, type Note } from './api'
import Icon from './Icon.vue'

const noteIcon = (k: string) => k === 'offline' ? 'refresh' : k === 'storage' ? 'home' : k === 'driver' ? 'switch' : 'sparkle'

/* a line is only worth reading if something can be done about it, so the ones that can carry the doing */
const retrying = ref('')
async function again(n: Note) {
  if (!n.retry || retrying.value) return
  retrying.value = n.retry
  try { store.status = await retryEntry(n.retry); await loadHealth(); notify('Asked it to try again.') }
  catch (e: any) { notify(e.message, 'error') }
  retrying.value = ''
}
</script>

<template>
  <div class="page">
    <p class="page-lede" v-if="store.notes.length">
      The house is running. These are the parts of it that have stopped answering, and each one
      says what it needs.
    </p>
    <ul class="recent notes" v-if="store.notes.length">
      <li v-for="(n, i) in store.notes" :key="i">
        <span class="recent-icon"><Icon :name="noteIcon(n.kind)" :size="16" /></span>
        <span class="recent-text">{{ n.text }}</span>
        <button v-if="n.flow" class="button small" @click="openFlow(n.flow)">{{ n.do || 'Sign in again' }}</button>
        <button v-else-if="n.retry" class="button small" :class="{ busy: retrying === n.retry }" :disabled="!!retrying" @click="again(n)">{{ n.do || 'Try again' }}</button>
        <button v-else-if="n.kind === 'update'" class="button small" @click="installUpdate">Try again</button>
        <span v-else></span>
      </li>
    </ul>
    <p class="empty" v-else>Nothing needs a look. Everything the house talks to is answering.</p>
  </div>
</template>
