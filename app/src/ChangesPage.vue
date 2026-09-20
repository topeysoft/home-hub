<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Who changed what. Reached from What happened, behind the code.
 *
 * What is in it is exactly what lock.needs_code() gates: if a route needed the
 * code to do the thing, the record of it having been done belongs on the same
 * side of the door. Turning a light on is not a change to the house and is not
 * here, which is also what keeps this short enough to be read rather than
 * scrolled past.
 *
 * Every sentence is the brain's (brain/hub/happened.py, class Changes). The one
 * thing this file is careful about is the WHO, and the care is all in what it
 * does not do: `named` says whether the house actually knew, and where it did
 * not the row says "Someone at the wall" rather than picking the likeliest
 * person. A plausible guess in an audit trail is worse than a blank, because a
 * blank cannot be believed by mistake.
 *
 * The card at the foot is the same rule as the memory card in docs/storage.md.
 * Before the code was set the house had no phones to tell apart, so nothing
 * before that date can name anybody -- and saying so once is more honest than a
 * column that is mysteriously empty for the first half of the list.
 */
import { computed, onMounted } from 'vue'
import { loadChanges, store } from './store'
import Icon from './Icon.vue'

const page = computed(() => store.changes)
const ICON: Record<string, string> = { phone: 'phone', share: 'share', bridge: 'wifi', draft: 'sparkle', home: 'home' }

onMounted(loadChanges)
</script>

<template>
  <div class="page">
    <p class="page-lede">
      Every change to the house, and which phone asked for it. Turning a light on is not a change to
      the house and is not here. Kept for a year.
    </p>

    <ul class="recent happened-over" v-if="page?.rows.length">
      <li v-for="(r, n) in page.rows" :key="`${r.ts}:${n}`">
        <span class="recent-icon"><Icon :name="ICON[r.kind] ?? 'home'" :size="16" /></span>
        <span class="recent-text happened-wrap">
          <b class="happened-who" :class="{ 'happened-unnamed': !r.named }">{{ r.who }}</b> {{ r.text }}
        </span>
        <span class="recent-when">{{ r.when }}</span>
      </li>
    </ul>

    <p class="page-lede happened-quiet" v-else-if="page">
      Nothing has been changed about the house yet.
    </p>

    <div class="happened-note" v-if="page?.coded_when">
      Before the code was set on <b>{{ page.coded_when }}</b> the house could not tell its phones
      apart, so the changes above that date say <b>Someone at the wall</b> and nothing more.
    </div>
  </div>
</template>
