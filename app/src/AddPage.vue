<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { ref } from 'vue'
import Adding from './Adding.vue'
import Icon from './Icon.vue'

/* Usually this page is for adding. It is also where a conversation the house already has open is
   picked up; the panel takes that on the way in and hands it here, so the page reads as being about
   that one job.

   ONE SURFACE PER CONVERSATION, NOTHING UNDER IT. While something is being added, this page draws
   nothing else at all -- no lede, no footnote. A half-asked question with the hub's health listed
   underneath it is a page talking over itself, and it is what this page used to do. The health
   itself moved to the hub's own page, where a person goes to ask about the hub rather than about a
   lamp. design/adding/Under.dc.html and design/adding/ChooseA.dc.html. */
defineProps<{ resume: string | null }>()
const busy = ref(false)
</script>

<template>
  <div class="page">
    <template v-if="!busy">
      <p class="page-lede" v-if="resume">The house remembers everything else about this one. This is the part only you can do.</p>
      <!-- "Then it turns up here" was a promise this page could not keep: nothing on it asked the
           hub to go and look, so it waited. It looks now, for as long as it is open. design/knock/. -->
      <p class="page-lede" v-else>Plug the new thing in and put it on the Wi‑Fi with its own app if it needs that. If it is already on, this will find it.</p>
    </template>
    <Adding :resume="resume" @busy="busy = $event" />
    <p class="add-elsewhere" v-if="!busy && !resume">
      <Icon name="clock" :size="17" />
      <span>Radios, the bridge and anything not working are under <b>Behind the scenes</b>, on the hub’s own page.</span>
    </p>
  </div>
</template>
