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
 *
 * The other line at the foot says when there is more behind this page. A list
 * that simply stops at its limit looks like a list that ended, and on the one
 * page whose whole job is completeness that is the worst thing it could imply.
 *
 * It is PAGED, and that is a fix as much as a nicety. Drawn in full, a real
 * house's year of changes came to 5331px of rows -- three to five times taller
 * than any other page in This house, and all of it inside the panel's
 * backdrop-filter. On that page, and only that page, scrolling left rows drawn
 * as bare icons with no text beside them: the element boxes painted and the
 * text and SVG did not. No page in this panel should be thousands of pixels
 * long, and an audit read newest-first has no reason to be.
 *
 * Paging narrowed that and did not close it: asking for older ones a few times
 * walks the page straight back past the height where it happens, which is
 * around eight thousand pixels. What closes it is in panel.css, on
 * `.happened-over li` -- the rows off screen are not drawn until they come near
 * -- and the reason is written there. Thirty at a time stays, for the reason it
 * was chosen: it is what somebody reads in one go.
 */
import { computed, onMounted, ref } from 'vue'
import { loadChanges, store } from './store'
import Icon from './Icon.vue'

const page = computed(() => store.changes)
/* A row with nothing to say draws as a bare icon with empty space beside it, which reads as the list
   having run out while it is still going. The brain is not supposed to send one -- happened.py falls
   back rather than dropping, and its tests hold that shut -- but this page is the one place a blank
   is visible, so it refuses to draw one whatever arrives. Belt and braces, on the page whose whole
   job is that you can believe what it shows you. */
const rows = computed(() => (page.value?.rows ?? []).filter(r => r?.text?.trim() && r?.who?.trim()))
const ICON: Record<string, string> = { phone: 'phone', share: 'share', bridge: 'wifi', draft: 'sparkle', home: 'home' }
/* Never an icon name Icon.vue does not have: an unknown one draws an empty square, and a column of
   empty squares is exactly what a broken row looks like. */
const iconFor = (kind: string) => ICON[kind] ?? 'home'

/* How many rows are drawn at once, and how many more each tap adds. Thirty is about two screens on a
   wall, which is the most anybody reads in one go and well under the height that broke the painting. */
const PAGE = 30
const shown = ref(PAGE)
const drawn = computed(() => rows.value.slice(0, shown.value))
const behind = computed(() => Math.max(0, rows.value.length - shown.value))

onMounted(loadChanges)
</script>

<template>
  <div class="page">
    <p class="page-lede">
      Every change to the house, and which phone asked for it. Turning a light on is not a change to
      the house and is not here. Kept for a year.
    </p>

    <ul class="recent happened-over" v-if="rows.length">
      <li v-for="(r, n) in drawn" :key="`${r.ts}:${n}`">
        <span class="recent-icon"><Icon :name="iconFor(r.kind)" :size="16" /></span>
        <span class="recent-text happened-wrap">
          <b class="happened-who" :class="{ 'happened-unnamed': !r.named }">{{ r.who }}</b> {{ r.text }}
        </span>
        <span class="recent-when">{{ r.when }}</span>
      </li>
    </ul>

    <p class="page-lede happened-quiet" v-else-if="page">
      Nothing has been changed about the house yet.
    </p>

    <button class="happened-more" v-if="behind" @click="shown += PAGE">
      <span>
        Show older changes
        <small>{{ behind === 1 ? '1 more' : `${behind} more` }}<template v-if="page?.coded_when">, back to {{ page.coded_when }}</template>. The house keeps them for a year.</small>
      </span>
      <Icon name="back" :size="16" class="flip happened-open" />
    </button>

    <p class="page-lede happened-quiet" v-else-if="page?.more">
      Showing the most recent changes. Older ones are kept for a year.
    </p>

    <div class="happened-note" v-if="page?.coded_when">
      Before the passcode was set on <b>{{ page.coded_when }}</b> the house could not tell its phones
      apart, so the changes above that date say <b>Someone at the wall</b> and nothing more.
    </div>
  </div>
</template>
