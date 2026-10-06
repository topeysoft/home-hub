<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed } from 'vue'
import { store } from '../store'
import Icon from '../Icon.vue'
import PhoneSteps from '../PhoneSteps.vue'

/*
 * A PART OF THE HOUSE. Beat two for the things the house is made of rather than the things it
 * switches on: another panel, and the bridge that brings in the switches already in the walls.
 *
 * Neither of these is let in from here, and that is the point of the screen rather than a gap in it.
 * A bridge KNOCKS: it is plugged in, it blinks, and the house comes and asks, wherever you are
 * standing. A panel is a phone or a tablet opening the house's address. So the honest thing to draw
 * is what to go and do, and the promise that the house takes it from there -- not a button that
 * pretends to do it.
 *
 * Both are on one screen because neither is a choice: a person came here to be told, and being made
 * to pick which telling they wanted would be a question with nothing behind it.
 *
 * design/adding/Spine.dc.html, and design/puck/Knock.dc.html for what happens next.
 */
/* A bridge already mid-conversation says so, because its own sheet is about to come up over this. */
const knocking = computed(() => store.bridge?.state === 'knocking')
</script>

<template>
  <p class="flow-desc">Both of these come to you: plug a bridge in, or open the house on a tablet, and the house asks you about it.</p>
  <h3 class="label">A bridge for your wall switches</h3>
  <p class="flow-desc" v-if="knocking">One is blinking amber nearby already. The house is about to ask whether it is yours &mdash; nothing of yours is on it until you say so.</p>
  <p class="flow-desc" v-else>Plug it into a socket between the hub and your wall switches. It blinks amber while it starts up, and the house asks you about it.</p>
  <div class="bridge-row" style="margin-bottom: 10px">
    <span class="bridge-icon"><Icon name="lock" :size="18" /></span>
    <span class="bridge-text"><span class="bridge-name">Nothing is added until you say so</span><span class="bridge-sub">A bridge that’s blinking has nothing of yours on it.</span></span>
  </div>
  <div class="bridge-row">
    <span class="bridge-icon"><Icon name="home" :size="18" /></span>
    <span class="bridge-text"><span class="bridge-name">Then find it a spot</span><span class="bridge-sub">A socket where it can reach your switches. The house tells you when it’s in a good place.</span></span>
  </div>
  <h3 class="label">Another screen</h3>
  <p class="flow-desc">Open the house on a tablet or phone and leave it there. Nothing to buy or install.</p>
  <PhoneSteps />
</template>
