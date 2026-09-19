<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Needs a look: the things the house cannot fix by itself.
 *
 * An account whose sign-in has expired, a radio that stopped, a thing that has
 * gone quiet, an update that failed. layout.ts calls this a strand because it
 * carries the only Sign in again a person has -- without it an expired account
 * can only be put right by opening Home Assistant, which is the thing this
 * panel exists not to need.
 *
 * It is a page of JOBS, and that is the whole design. Before, it was a page of
 * true sentences with two buttons on it: six of the nine lines a real house was
 * showing had no way forward at all, and the ninth -- the dead radio that had
 * caused the other six -- read last, as if it were the least of them. Somebody
 * tapped "8 things need a look" and got a report.
 *
 * So the brain now hands over jobs and the panel just draws them (health.py).
 * Two things follow from that, and both live there rather than here:
 *
 *   The cause is the line. A fault carries what went quiet with it in `with`,
 *   so one dead radio is one row and not seven, and the six names sit under it
 *   where a person can see it is their front door and their dimmer. Fixing the
 *   one clears all of them, which is why they are not rows of their own.
 *
 *   Every row carries its own `acts` -- including the WORDS on the buttons.
 *   The panel does not know what it is looking at and so decides nothing here;
 *   a row with nothing to offer is a gap in the brain, not in this file.
 *
 * What this file does own is the asking. Anything that cannot be taken back
 * (removing a thing from the house) goes through the two-tap the rest of the
 * panel uses: the first tap turns the button into the question with the name in
 * it, the second does it. Nothing vanishes under one tap.
 */
import { computed, ref } from 'vue'
import { installUpdate, loadHealth, notify, openFlow, restartHub, store } from './store'
import { checkDevice, forgetBridge, forgetDevice, retryEntry, retryPart, type Act, type Note, type Rung } from './api'
import Icon from './Icon.vue'

const noteIcon = (k: string) => k === 'offline' || k === 'restart' ? 'refresh' : k === 'storage' ? 'home' : k === 'driver' ? 'switch' : k === 'bridge' ? 'wifi' : 'sparkle'

/* A long list of quiet things folds, because five is enough to see the shape of it -- but the fold opens.
   The old list stopped at five in the BRAIN and ended with "And 3 more things are offline", a sentence
   with nowhere to go; a fold is only honest when the thing behind it can be reached. Faults, storage and
   a failed update are never folded: they are the jobs somebody came here for. */
const SHOWN = 5
const open = ref(false)
const quiet = computed(() => store.notes.filter(n => n.kind === 'offline').length)
const more = computed(() => Math.max(0, quiet.value - SHOWN))
const shown = computed(() => {
  if (open.value || !more.value) return store.notes
  let seen = 0
  return store.notes.filter(n => n.kind !== 'offline' || ++seen <= SHOWN)
})

/* what went quiet behind a fault: the first few by name, the rest one tap away */
const NAMED = 3
const spread = ref<Record<string, boolean>>({})
const key = (n: Note, i: number) => `${n.kind}:${n.subject ?? i}`

const busy = ref('')      // the act that is running; one at a time, so a second tap cannot race the first
const asking = ref('')    // the act whose question is up, waiting for the second tap

async function run(n: Note, a: Act, id: string) {
  if (a.ask && asking.value !== id) { asking.value = id; return }   // first tap asks, with the name in it
  asking.value = ''
  if (a.act === 'flow') return openFlow(a.to!)
  if (a.act === 'update') return installUpdate()
  /* A restart takes this page away with it, so there is nothing to refresh afterwards and nothing to
     mark busy: the overlay is up before the tap has finished. The rung is the brain's -- this page
     offers whichever one it was given, and the question above it came from there too. */
  if (a.act === 'restart') return void restartHub(a.to as Rung)
  if (busy.value) return
  busy.value = id
  try {
    if (a.act === 'entry') { store.status = await retryEntry(a.to!); notify('Asked it to try again.') }
    else if (a.act === 'part') { await retryPart(a.to!); notify('Asked it to try again.') }
    else if (a.act === 'check') { const r = await checkDevice(a.to!); notify(r.text, r.answering ? 'info' : 'error') }
    else if (a.act === 'forget') {
      await forgetDevice(a.to!)
      notify(n.name ? `${n.name} is forgotten.` : 'It is forgotten.')
      store.notes = store.notes.filter(x => x.subject !== a.to)   // it goes now; the next rebuild agrees
    }
    /* A bridge, not a device: it was never in the house's device list to remove from. What goes with
       it is its retained topics, which is the brain's job -- without that it would be back in the
       list the next time the brain starts. */
    else if (a.act === 'bridge') {
      const r = await forgetBridge(a.to!)
      notify(`${r.forgotten} is forgotten.`)
      store.notes = store.notes.filter(x => x.subject !== a.to)
    }
    await loadHealth()
  } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
</script>

<template>
  <div class="page">
    <p class="page-lede" v-if="store.notes.length">
      The house is running. These are the parts of it that have stopped answering. Each one says what it
      needs and what you can do about it from here.
    </p>
    <ul class="recent notes" v-if="store.notes.length">
      <li v-for="(n, i) in shown" :key="key(n, i)" :class="{ fault: !!n.with?.length }">
        <span class="recent-icon"><Icon :name="noteIcon(n.kind)" :size="16" /></span>
        <span class="recent-text">
          {{ n.text }}
          <!-- where to go and look: the room and what sort of thing it is. A name on its own is a riddle. -->
          <small class="note-where" v-if="n.where">{{ n.where }}</small>
          <!-- what went quiet behind this one fault; put the fault right and these come back together -->
          <small class="note-with" v-if="n.with?.length">
            {{ n.with.length === 1 ? 'One thing went quiet with it:' : `${n.with.length} things went quiet with it:` }}
            <template v-if="spread[key(n, i)]">
              <span class="note-thing" v-for="w in n.with" :key="w.id">{{ w.name }}<span class="note-thing-where" v-if="w.where">{{ w.where }}</span></span>
            </template>
            <template v-else>
              <!-- the comma rides inside the interpolation: a whitespace-only text node between a mustache
                   and a tag is condensed away, and "Home Theater Lightand 3 more" is what that looks like -->
              {{ n.with.slice(0, NAMED).map(w => w.name).join(', ') + (n.with.length > NAMED ? ', ' : '') }}
              <button v-if="n.with.length > NAMED" class="linky" @click="spread[key(n, i)] = true">and {{ n.with.length - NAMED }} more</button>
            </template>
          </small>
        </span>
        <span class="note-acts">
          <template v-for="(a, j) in (n.acts || [])" :key="j">
            <span class="note-ask" v-if="a.ask && asking === `${key(n, i)}:${j}`">
              {{ a.ask }}
              <button class="button small" :class="{ busy: busy === `${key(n, i)}:${j}` }" @click="run(n, a, `${key(n, i)}:${j}`)">{{ a.yes || a.do }}</button>
              <button class="button small ghost" @click="asking = ''">{{ a.no || 'Keep it' }}</button>
            </span>
            <button v-else-if="!asking.startsWith(key(n, i) + ':')" class="button small" :class="{ ghost: j > 0, busy: busy === `${key(n, i)}:${j}` }"
                    :disabled="!!busy" @click="run(n, a, `${key(n, i)}:${j}`)">{{ a.do }}</button>
          </template>
        </span>
      </li>
    </ul>
    <button class="button small ghost more-quiet" v-if="more && !open" @click="open = true">
      Show the other {{ more }} {{ more === 1 ? 'thing' : 'things' }} that are offline
    </button>
    <p class="empty" v-else-if="!store.notes.length">Nothing needs a look. Everything the house talks to is answering.</p>
  </div>
</template>
