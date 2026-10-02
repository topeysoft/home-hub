<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Move this phone (design/away/, NamedC-move). What the band line opens, on every phone of the house, once:
 * the house has an address of its own, and this carries the phone to it. Nothing about being let out is on
 * it -- that is the switch on People, for later and for whoever keeps the house.
 *
 * The first step is the only one the page can do: a one-time code from the hub, here at home, and the phone
 * opens the house's own name with it. The other two are the phone's own -- Add to Home Screen, then the old
 * icon away -- so they are said, not done.
 */
import { ref } from 'vue'
import { startMove } from './api'
import { store } from './store'
import Icon from './Icon.vue'

const busy = ref(false), error = ref('')
const address = (store.me?.address ?? '').replace(/^https:\/\//, '')
async function go() {
  busy.value = true; error.value = ''
  try { location.href = (await startMove()).url }
  catch (e: any) { error.value = e.message; busy.value = false }
}
</script>

<template>
  <main class="setup move">
    <section class="setup-page">
      <span class="setup-mark"><Icon name="globe" :size="30" /></span>
      <h1 class="display">A new link for the house.</h1>
      <p class="setup-lede">The house has its own web address now: <b>{{ address }}</b>. Switch this phone to it once, and the same icon works at home, and anywhere once this phone is set to Anywhere.</p>
      <ol class="move-steps">
        <li><span class="move-n">1</span><span><b>Switch this phone</b><span class="move-s">It opens the house at the new link. Nothing to type.</span></span></li>
        <li><span class="move-n">2</span><span><b>Add it to your Home Screen</b><span class="move-s">Share, then Add to Home Screen.</span></span></li>
        <li><span class="move-n">3</span><span><b>Delete the old icon</b><span class="move-s">The new one works at home too.</span></span></li>
      </ol>
      <p class="error" v-if="error">{{ error }}</p>
      <div class="setup-actions">
        <button class="button big" :class="{ busy }" @click="go">Switch this phone</button>
        <button class="button ghost" @click="store.moving = false">Not now</button>
      </div>
    </section>
  </main>
</template>
