<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Move this phone (design/houses/, MoveToApp; until 3 October, design/away/ NamedC-move). What the band line
 * opens, on every phone of the house, once: the house has an address of its own, and this carries the phone
 * into the Houses app, where every house it joins is kept. Nothing about being let out is on it -- that is
 * the switch on People, for later and for whoever keeps the house.
 *
 * The first step is the only one the page can do: a one-time code from the hub, here at home, and the phone
 * opens the app with it. The other two are the phone's own -- Add to Home Screen, then the old icon away --
 * so they are said, not done.
 */
import { ref } from 'vue'
import { startMove } from './api'
import { store } from './store'
import Icon from './Icon.vue'
import { appHost } from './move'

const busy = ref(false), error = ref('')
const address = appHost(store.me?.address)
async function go() {
  busy.value = true; error.value = ''
  try { location.href = (await startMove()).url }
  catch (e: any) { error.value = e.message; busy.value = false }
}
</script>

<template>
  <main class="setup move">
    <section class="setup-page">
      <span class="setup-mark"><Icon name="home" :size="30" /></span>
      <h1 class="display">One app for your houses.</h1>
      <p class="setup-lede">Switch this phone to <b>{{ address }}</b> once. This house is in it, and any other house you join goes there too.</p>
      <ol class="move-steps">
        <li><span class="move-n">1</span><span><b>Switch this phone</b><span class="move-s">It opens Houses, with this house in it.</span></span></li>
        <li><span class="move-n">2</span><span><b>Add it to your Home Screen</b><span class="move-s">Share, then Add to Home Screen.</span></span></li>
        <li><span class="move-n">3</span><span><b>Delete the old icon</b><span class="move-s">Houses works at home too.</span></span></li>
      </ol>
      <p class="error" v-if="error">{{ error }}</p>
      <div class="setup-actions">
        <button class="button big" :class="{ busy }" @click="go">Switch this phone</button>
        <button class="button ghost" @click="store.moving = false">Not now</button>
      </div>
    </section>
  </main>
</template>
