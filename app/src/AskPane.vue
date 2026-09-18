<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * A phone on the Wi-Fi is asking to join, as a pane rather than as a card in a
 * strip.
 *
 * The panel already ranked this above everything else it can tell you and then
 * rendered it as though it had not. App.vue wakes the wall when the asks grow
 * -- it is the ONE event worth turning the screen back on for -- and the card
 * this replaces carried a comment saying it must look the same at every hour,
 * because it is the one place a person hands out keys to the house and
 * recognising it instantly is the only defence against answering a prompt they
 * should not. Then it sat in a row underneath "An update is ready", in the same
 * shape, on the same ground.
 *
 * A pane is what the panel already uses for something that needs you now: it
 * rises from the bottom, the room dims behind it, and it is unmissable from
 * across a room -- which is the point, since the person holding the phone is
 * standing there waiting. It also costs the layout nothing, because a pane is
 * over the arrangement rather than in it, which is how Wall's row keeps the
 * height it was drawn with.
 *
 * One phone at a time, oldest first. That is not a simplification: this is a
 * decision about one device, and a list of them invites answering the lot with
 * one tap.
 *
 * The way out is `aside`, not `deny`. Putting a knock aside leaves it standing
 * -- the chip in the band carries it and opens this again -- because a person
 * who wants to look at something else first must not have to choose between
 * denying a phone and being stuck. Only the two buttons decide anything.
 *
 * Its colour does not follow the sky, and panel.css says why at more length.
 * Everything else here -- the rise, the fall, the room going quiet -- is the
 * pane the face already measured in design/nightfall slice 5.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify } from './store'
import { allowPhone, denyPhone, type Ask } from './api'
import Icon from './Icon.vue'

const ask = computed<Ask | null>(() => store.asks[0] ?? null)
const waiting = computed(() => Math.max(0, store.asks.length - 1))
const choosing = ref(false), busy = ref(false)

const SPANS = [['day', 'For today'], ['weekend', 'For the weekend'], ['keep', 'Keep']] as const

const shown = ref(false)
/* the same two facts, and the same two frames, as a device opening: `closing` is
   not `!shown`, because for two frames at the start a pane is also not shown and
   the stylesheet counts the bottom bar's way back from the fall beginning */
const closing = ref(false)
function fall(then: () => void) {
  shown.value = false; closing.value = true
  setTimeout(then, 320)
}
function rise() {
  closing.value = false
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))
}
function aside() { fall(() => (store.askAside = true)) }

/* Answering is the end of it. The pane used to stand there afterwards showing the same phone and the
   same two buttons, because it only leaves when the hub says the ask is gone -- and the hub does not
   say so until the phone itself picks the key up, which can be a while and, when the person let it in,
   was not being said at all. Whichever way it goes, the fall starts on the tap: the decision is made
   here, the toast carries the word, and a question already answered must not be left on a wall for
   somebody else to answer again.

   The ask is dropped locally rather than waiting for the phones event, so this holds even if that
   event never arrives. When another phone is behind it the pane rises again with the next one, one at
   a time, arriving the way this one did -- not sitting there already open on a new name. */
function answered(id: string) {
  fall(() => {
    store.asks = store.asks.filter(a => a.id !== id)
    choosing.value = false; busy.value = false
    if (store.asks.length) rise()
  })
}

async function allow(span: 'day' | 'weekend' | 'keep') {
  const a = ask.value; if (!a || busy.value) return
  busy.value = true
  try {
    await allowPhone(a.id, span)
    notify(`${a.name} is in${span === 'day' ? ' for today' : span === 'weekend' ? ' for the weekend' : ''}.`)
    answered(a.id)
  } catch (e: any) {
    // the code was asked for and not given, or the hub said no: the question stands, so the pane does
    if (e.message !== 'That needs the code.') notify(e.message, 'error')
    choosing.value = false; busy.value = false
  }
}
async function deny() {
  const a = ask.value; if (!a || busy.value) return
  busy.value = true
  try { await denyPhone(a.id); answered(a.id) }
  catch (e: any) { if (e.message !== 'That needs the code.') notify(e.message, 'error'); busy.value = false }
}

/* A wall panel has no keyboard, so Escape is not the way out and never the only
   one -- the veil and the close both put this aside. It is here for the desk. */
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') aside() }
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="opened ask-pane" :class="{ shown, closing }" v-if="ask" role="dialog" :aria-label="`${ask.name} wants to join the house`">
    <div class="opened-veil" @click="aside"></div>
    <div class="opened-panel">
      <button class="back opened-close" @click="aside" aria-label="Put this aside"><Icon name="close" :size="18" /></button>

      <span class="opened-hero" aria-hidden="true"><Icon name="phone" :size="260" /></span>

      <div class="opened-body">
        <div class="opened-step s0">
          <div class="opened-room">A phone on the Wi‑Fi</div>
          <h2 class="display opened-name">{{ ask.name }} wants to join the house</h2>
        </div>

        <div class="opened-step s1 ask-says">
          <p v-if="!choosing">Let it in and it can run the house from the Wi‑Fi — the lights, the locks, everything this
            screen can do. It starts home‑only. If you are not sure whose phone this is, say not now.</p>
          <p v-else>For how long? A phone let in for today is out again tonight, and you can change any of this later
            under People and phones.</p>
        </div>

        <div class="opened-step s2 ask-acts" v-if="!choosing">
          <button class="button big" @click="choosing = true">Let it in</button>
          <button class="button big ghost" @click="deny">Not now</button>
        </div>
        <div class="opened-step s2 ask-acts" v-else>
          <button class="button big" v-for="[k, l] in SPANS" :key="k" :class="{ busy, ghost: k !== 'keep' }" @click="allow(k)">{{ l }}</button>
          <button class="button big ghost ask-back" @click="choosing = false">Back</button>
        </div>

        <p class="opened-step s3 ask-more" v-if="waiting">
          {{ waiting === 1 ? 'One more phone is waiting' : `${waiting} more phones are waiting` }}. They come one at a time.
        </p>
      </div>
    </div>
  </div>
</template>
