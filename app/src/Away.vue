<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Reached from outside the house, and the house did not open. One sentence, and it is the brain's:
 * a phone this house knows is told it is set to Home only and who can change that, and anyone else is told
 * nothing they could act on, because from out here the way in does not exist (docs/away.md, piece 2).
 *
 * For a phone the house knows it is also a wait, not a dead end (design/away/, NamedC-out): Sam at the
 * airport asks, Temi picks Anywhere for it on People, and this screen opens by itself -- it asks again
 * every few seconds, and the moment the answer is yes the house loads. Anyone else has nothing to wait for,
 * so nothing is asked again. There is nothing to tap either way.
 */
import { computed, onMounted, onUnmounted } from 'vue'
import { getMe } from './api'
import { lock } from './code'
import { waitsToBeLetOut } from './move'
import Icon from './Icon.vue'

const waits = computed(() => waitsToBeLetOut(lock.away))
let poll: number | undefined
onMounted(() => {
  if (!waits.value) return
  poll = window.setInterval(async () => {
    try {
      const me = await getMe()
      if (me.paired && me.phone?.remote) { clearInterval(poll); lock.away = null; location.reload() }
    } catch { /* still outside and still not let out; ask again in a moment */ }
  }, 5000)
})
onUnmounted(() => clearInterval(poll))
</script>

<template>
  <main class="setup away">
    <section class="setup-page">
      <span class="setup-mark"><Icon name="home" :size="30" /></span>
      <h1 class="display">{{ waits ? 'Set to Home only.' : 'Not open to this phone.' }}</h1>
      <p class="setup-lede">{{ lock.away }}</p>
      <p class="setup-status" v-if="waits"><span class="pulse-dot"></span> This opens by itself as soon as they do.</p>
      <p class="setup-foot">Back on your home Wi‑Fi, it works as it always does.</p>
    </section>
  </main>
</template>
