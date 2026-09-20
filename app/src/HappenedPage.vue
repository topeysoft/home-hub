<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * What happened: the catch-up for somebody who has just walked in.
 *
 * The idea this page exists to carry is that a finding is a SPAN, not an event.
 * "The porch light has been on for ten hours" is the news. The log holds
 * transitions, so that fact is the distance between two rows that may be ten
 * hours and forty rows apart -- which is why a plain timeline could not show it
 * and why this is not one. brain/hub/happened.py does the measuring.
 *
 * This file draws what it is handed and decides nothing, the same way
 * NotesPage.vue does and for the same reason: the panel does not know what it
 * is looking at. That goes for the group HEADINGS too. "Still on" is right over
 * two lights and wrong over a door that is still unlocked, so the brain names
 * the group from what is actually in it and hands the words over.
 *
 * The ranking is the design. What is still true leads and carries the only
 * buttons on the page; what is over reads quietly under it with none, because
 * a door that locked itself at 6:40am is not a job and a button against it
 * would be offering to do something that has already happened.
 *
 * Nothing vanishes under a tap. Turning the porch light off leaves its row
 * exactly where it was, saying what it now says, with the way back in it --
 * the row is the undo. Re-reading the page from the brain would be the obvious
 * thing and is the wrong one: the finding would disappear mid-tap, taking the
 * heading and everything under it up the screen.
 */
import { computed, onMounted, ref } from 'vue'
import { ago, describe, loadHappened, notify, store } from './store'
import { act, getEvents, type HappenedAct, type HappenedItem } from './api'
import { didWhat, iconFor } from './happened'
import Icon from './Icon.vue'

const page = computed(() => store.happened)
const busy = ref('')                                   // the act that is running; one at a time
const done = ref<Record<string, string>>({})           // subject -> what this page just did to it

const key = (i: HappenedItem, n: number) => `${i.kind}:${i.subject}:${n}`

async function run(i: HappenedItem, a: HappenedAct, id: string) {
  if (a.act === 'room') {                              // nothing closes a door over the network: go and look
    store.goRoom = a.to
    store.sheet = null
    return
  }
  if (busy.value) return
  busy.value = id
  try {
    await act(a.to, a.arg ?? 'off')
    /* The row stays, and says what it now says. The house will agree on the next stream message;
       this is so the screen agrees at the moment of the tap rather than a beat later. */
    done.value[i.subject] = didWhat(a.arg)
  } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}

/* Everything that happened: the log itself, for the curious, folded because it is not what anybody
   came here for. It is drawn with the same describe() that writes Recently on Home rather than a
   second renderer -- one place decides what a state change reads like, and this is not it. */
const all = ref<{ key: number; text: string; icon: string; when: string }[] | null>(null)
const opening = ref(false)
async function openLog() {
  if (all.value) { all.value = null; return }          // a second tap folds it again
  opening.value = true
  try {
    const tick = Date.now()
    all.value = (await getEvents(200)).flatMap(e => {
      const d = describe(e)
      return d ? [{ key: e.ts, text: d.text, icon: d.icon, when: ago(e.ts, tick) }] : []
    })
  } catch (e: any) { notify(e.message, 'error') }
  opening.value = false
}

onMounted(loadHappened)
</script>

<template>
  <div class="page">
    <p class="page-lede" v-if="page">{{ page.lede }}</p>

    <template v-if="page">
      <section v-for="g in page.groups" :key="g.id" class="happened-group">
        <h2 class="label" :class="{ 'happened-live': g.id === 'still' }">{{ g.label }}</h2>

        <!-- still: a card each, because each one carries a button -->
        <ul class="recent notes" v-if="g.id === 'still'">
          <li v-for="(i, n) in g.items" :key="key(i, n)">
            <span class="recent-icon happened-warm"><Icon :name="iconFor(i)" :size="16" /></span>
            <span class="recent-text">
              {{ i.text }}
              <small class="note-where" v-if="i.where">{{ i.where }}</small>
              <!-- what this page just did, kept where the thing was: the row is the undo -->
              <small class="happened-did" v-if="done[i.subject]">{{ done[i.subject] }}</small>
            </span>
            <span class="note-acts">
              <button v-for="(a, j) in i.acts" :key="j" class="button small" :class="{ ghost: j > 0, busy: busy === key(i, n) }"
                      :disabled="!!busy || !!done[i.subject]" @click="run(i, a, key(i, n))">{{ a.do }}</button>
            </span>
          </li>
        </ul>

        <!-- over, and the phones: a line each, no buttons, nothing to do -->
        <ul class="recent happened-over" v-else>
          <li v-for="(i, n) in g.items" :key="key(i, n)">
            <span class="recent-icon"><Icon :name="iconFor(i)" :size="16" /></span>
            <span class="recent-text happened-wrap">{{ i.text }}</span>
            <span class="recent-when">{{ i.when }}</span>
          </li>
        </ul>
      </section>

      <p class="page-lede happened-quiet" v-if="page.empty">
        Nothing worth catching up on. Nothing has been left on, no door has been left open, and
        nobody new has joined the house.
      </p>

      <!-- the two folds: the full log for the curious, and the audit behind the code -->
      <button class="happened-more" :class="{ busy: opening }" @click="openLog">
        <span>
          Everything that happened
          <small>Every line the house wrote down, newest first. Kept for 30 days.</small>
        </span>
        <Icon name="back" :size="16" class="flip" :class="{ 'happened-open': !!all }" />
      </button>
      <ul class="recent happened-log" v-if="all">
        <li v-for="e in all" :key="e.key">
          <span class="recent-icon"><Icon :name="e.icon" :size="16" /></span>
          <span class="recent-text">{{ e.text }}</span>
          <span class="recent-when">{{ e.when }}</span>
        </li>
        <li v-if="!all.length"><span class="recent-text">Nothing written down yet.</span></li>
      </ul>

      <button class="happened-more" @click="store.sheet = 'changes'">
        <span>
          Who changed what
          <span class="happened-gated"><Icon name="lock" :size="12" />needs the code</span>
          <small>Renames, rooms, accounts, routines and phones — and which phone asked.</small>
        </span>
        <Icon name="back" :size="16" class="flip" />
      </button>
    </template>
  </div>
</template>
