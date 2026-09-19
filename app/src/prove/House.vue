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
  <p class="flow-desc">These two let you in rather than the other way round: plug one in, or open the house on it, and it comes to you.</p>

  <h3 class="label">A bridge for your switches</h3>
  <p class="flow-desc" v-if="knocking">One is blinking amber nearby already. The house is about to ask whether it is yours &mdash; nothing of yours is on it until you say so.</p>
  <p class="flow-desc" v-else>Plug it into a socket between the hub and your switches. It blinks amber while it looks around, and the house asks you about it the moment it does.</p>
  <div class="bridge-row" style="margin-bottom: 10px">
    <span class="bridge-icon"><Icon name="lock" :size="18" /></span>
    <span class="bridge-text"><span class="bridge-name">Nothing is let in until you say so</span><span class="bridge-sub">A bridge that is knocking is only knocking. It has nothing of yours on it.</span></span>
  </div>
  <div class="bridge-row">
    <span class="bridge-icon"><Icon name="home" :size="18" /></span>
    <span class="bridge-text"><span class="bridge-name">Then it wants a home of its own</span><span class="bridge-sub">A socket it can stay in, where it can hear your switches. The house says when it can.</span></span>
  </div>

  <h3 class="label">Another panel</h3>
  <p class="flow-desc">A panel is the house’s own address, opened on a phone or a tablet and kept there. Nothing to install from a shop.</p>
  <PhoneSteps />
</template>
