<script setup lang="ts">
/*
 * Reached from outside the house, and the house did not open. One sentence, and it is the brain's:
 * a phone this house knows is told that somebody at the wall can let it out, and anyone else is told
 * nothing they could act on, because from out here the way in does not exist (docs/away.md, piece 2).
 *
 * There is nothing to try, so there is nothing to tap. The house is still there on its own Wi-Fi,
 * which is the one thing worth saying next.
 */
import { lock } from './code'
import Icon from './Icon.vue'
</script>

<template>
  <main class="setup away">
    <section class="setup-page">
      <span class="setup-mark"><Icon name="home" :size="30" /></span>
      <h1 class="display">Not from here.</h1>
      <p class="setup-lede">{{ lock.away }}</p>
      <p class="setup-foot">On the house's own Wi‑Fi this phone opens it as it always does.</p>
    </section>
  </main>
</template>
