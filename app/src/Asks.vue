<script setup lang="ts">
/* A phone on the Wi‑Fi asked to join. The deciding happens in AskPane.vue, which rises on its own
   the moment a knock arrives; this is what is left in the band once somebody has put that pane
   aside, and its only job is to make sure the knock is never lost. Tapping it brings the pane back.

   So this is a chip and not a card, and it is the one chip in the band that wears the attention
   colour, because the two things in the band are not the same kind of thing: an update is an offer
   and a phone at the door is a person waiting. It is still never the ONLY way to answer -- the pane
   opens itself -- which is what keeps it honest about the strand layout.ts says must be carried. */
import { store } from './store'
import Icon from './Icon.vue'

const name = () => store.asks[0]?.name ?? 'A phone'
</script>

<template>
  <button class="nudge ask attention" v-if="store.asks.length && store.askAside" @click="store.askAside = false">
    <span class="nudge-icon"><Icon name="phone" :size="20" /></span>
    <span class="nudge-text">
      <span class="nudge-title">{{ store.asks.length > 1 ? `${store.asks.length} phones want to join` : `${name()} wants to join the house` }}</span>
      <span class="nudge-sub">Waiting on you. Tap to let it in, or to say not now.</span>
    </span>
  </button>
</template>
