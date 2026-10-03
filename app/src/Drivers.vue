<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { failed } from './code'
import { computed, ref } from 'vue'
import { store, notify } from './store'
import { retryEntry } from './api'

/* What is running behind the panel, in plain words: the radios, Matter, Ring. The brain connects
   each one to the engine itself; the only thing a person ever does here is sign in to Ring. Things
   that were added but could not connect (a Nest without its API enabled) show here too, with the
   reason and a way to try again once it is fixed. */
/* On first run (needs-you) only what needs the person shows, in a sentence rather than a status: the rest of
   the machinery is on This hub, and first run says as little as it can (design/words-setup/, B). */
const props = defineProps<{ needsYou?: boolean }>()
const all = computed(() => store.status?.drivers ?? [])
const parts = computed(() => props.needsYou ? all.value.filter(p => p.state === 'sign-in' || p.state === 'failed') : all.value)
const said = (p: { name: string; state: string; text: string }) => !props.needsYou ? { name: p.name, sub: p.text }
  : p.state === 'sign-in' ? { name: `${p.name} needs you to sign in`, sub: 'Its devices join the house once you do.' } : { name: `${p.name} isn’t working`, sub: p.text }
const problems = computed(() => store.status?.problems ?? [])
const attention = computed(() => problems.value.length > 0 || all.value.some(p => p.state === 'sign-in' || p.state === 'failed'))
const link = (port: number) => `${location.protocol}//${location.hostname}:${port}`
const retrying = ref<string | null>(null)
async function retry(id: string) {
  retrying.value = id
  try { store.status = await retryEntry(id); if (!store.status.problems?.some(p => p.entry_id === id)) notify('Connected.') }
  catch (e: any) { notify(failed('Still not connecting', e), 'error') }
  retrying.value = null
}
defineExpose({ attention })
</script>

<template>
  <ul class="drivers" v-if="parts.length || problems.length">
    <li v-for="p in parts" :key="p.id" :class="p.state">
      <span class="drv-dot"></span>
      <span class="drv-text"><span class="drv-name">{{ said(p).name }}</span><span class="drv-sub">{{ said(p).sub }}</span></span>
      <a v-if="p.state === 'sign-in'" class="button small" :href="link(p.port)" target="_blank" rel="noopener">Sign in</a>
    </li>
    <li v-for="q in problems" :key="q.entry_id" class="failed">
      <span class="drv-dot"></span>
      <span class="drv-text"><span class="drv-name">{{ q.title }}</span><span class="drv-sub">{{ q.reason || 'Could not connect.' }}</span></span>
      <button class="button small" :class="{ busy: retrying === q.entry_id }" @click="retry(q.entry_id)">Try again</button>
    </li>
  </ul>
</template>
