<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Share this house: what Apple Home, Google Home and Alexa are allowed to see. docs/matter.md.
 *
 * Three things this screen is shaped by, and each is a decision made before it:
 *
 *   - NOTHING IS SHARED UNTIL SOMEBODY SAYS SO. The first switch is off, and while it is off there is
 *     no bridge running at all -- so this page starts as one line and a switch, not as a list of
 *     ecosystems to scroll past.
 *   - THE DOOR IS SHUT. A Matter bridge with an open window and a printed code will join whoever has
 *     the code, so the code is behind a tap, is shown for five minutes, and shuts itself.
 *   - THE LOCK SWITCH IS ITS OWN, WITH THE RISK IN THE SENTENCE BESIDE IT. Matter carries the unlock
 *     with the lock and there is no half to publish, so this is the one place the panel says out loud
 *     what a household is agreeing to.
 *
 * What is NOT here: a list of every device. A kind is what somebody decides about; a hundred rows of
 * lamps is the list this panel keeps refusing to draw.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { openShareWindow, setShare, shareQrUrl } from './api'
import { loadShare, notify, store } from './store'
import Icon from './Icon.vue'

const share = computed(() => store.share)
const busy = ref('')
const qrBroken = ref(false)
const tick = ref(0)
let poll: number | undefined

/* The words for a kind, in the plural a person would say. The hub decides WHICH kinds it can publish
   (`offer`); this only knows how to say them, and anything it has no word for is shown as the hub's
   own word rather than hidden -- a kind this panel has never heard of is still the household's. */
const WORDS: Record<string, { name: string; hint: string }> = {
  light: { name: 'Lights', hint: 'Every lamp and ceiling light, dimmable where it can dim.' },
  switch: { name: 'Plugs and switches', hint: 'Anything that is only on or off.' },
  appliance: { name: 'Appliance features', hint: 'An ice maker, a delay start: part of a machine rather than a plug.' },
  fan: { name: 'Fans', hint: 'Fans, with their speed.' },
  cover: { name: 'Blinds and curtains', hint: 'Blinds, curtains and shades. A garage door is not one of these — it has its own switch below.' },
  climate: { name: 'Thermostats', hint: 'The temperature it is set to, and whether it is heating or cooling.' },
  motion: { name: 'Motion sensors', hint: 'Whether there is somebody in the room.' },
  contact: { name: 'Door and window sensors', hint: 'Whether a door or a window is open.' },
  'sensor.temperature': { name: 'Temperature', hint: 'What each room is reading.' },
  'sensor.humidity': { name: 'Humidity', hint: 'How damp each room is.' },
}
const word = (k: string) => WORDS[k] ?? { name: k.charAt(0).toUpperCase() + k.slice(1), hint: '' }

const held = computed(() => share.value?.holders ?? [])

/* The map at the top of the page. It draws THIS house -- a kettle on the left, Apple Home on the
   right -- because "your devices become Matter devices" is an abstraction until you see your own
   kettle in it, and this page has to argue the feature to somebody who has never heard of Matter. */
const APPS = ['Apple Home', 'Google Home', 'Alexa']
const ICON: Record<string, string> = { light: 'light', switch: 'switch', appliance: 'appliance' }
const preview = computed(() => share.value?.preview ?? [])
const count = computed(() => (share.value?.on ? share.value.shared : share.value?.candidates) ?? 0)
const more = computed(() => Math.max(0, count.value - preview.value.length))
const holding = (name: string) => held.value.some(h => h.name === name)
/* Is there actually a bridge behind this page. The hub decides -- it knows when the bridge last
   reported, and a bridge that has stopped saying anything is not one that is running. Without this
   the page offered to open a door with nothing behind it and said it had. */
const running = computed(() => !!share.value?.bridge?.running)
const stopped = computed(() => !!share.value?.on && !running.value)
const heldLine = computed(() => {
  const names = held.value.map(h => h.name)
  if (!names.length) return ''
  if (names.length === 1) return names[0]
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
})
/* The value line answers the question the row exists for: is anything leaving this house, and to whom. */
const summary = computed(() => {
  const s = share.value
  if (!s) return ''
  if (!s.on) return 'Off. Nothing about this house leaves it.'
  const things = s.shared === 1 ? '1 thing' : `${s.shared} things`
  const out = s.left_out_now ? ` ${s.left_out_now} kept home.` : ''
  return (held.value.length ? `${things}, shared with ${heldLine.value}.` : `${things} ready. None added yet.`) + out
})
/* The countdown runs on this screen rather than being asked for every second: the hub said how long
   was left when the door opened, and a clock is the one thing a panel can be trusted to do on its own. */
const left = computed(() => {
  void tick.value
  const s = seconds.value
  return s == null || s <= 0 ? '' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})
const seconds = ref<number | null>(null)

async function refresh() {
  await loadShare()
  seconds.value = store.share?.seconds_left ?? null
}
async function change(body: { on?: boolean; kinds?: string[]; locks?: boolean }, what: string) {
  if (busy.value) return
  busy.value = what
  try { store.share = await setShare(body) } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
const flip = () => change({ on: !share.value?.on }, 'on')
function flipKind(k: string) {
  const kinds = share.value?.kinds ?? []
  change({ kinds: kinds.includes(k) ? kinds.filter(x => x !== k) : [...kinds, k] }, k)
}
const flipLocks = () => change({ locks: !share.value?.locks }, 'locks')
/* What the kinds that are on actually mean, in their own words, so the row explains itself without a
   hint under every chip. Nothing on says so plainly rather than leaving the line empty. */
const kindsHint = computed(() => {
  const s = share.value
  if (!s) return ''
  const on = s.offer.filter(k => s.kinds.includes(k))
  return on.length ? on.map(k => word(k).hint).filter(Boolean).join(' ') : 'Nothing is going out.'
})
async function addApp() {
  if (busy.value) return
  busy.value = 'window'
  qrBroken.value = false
  try { store.share = await openShareWindow(); seconds.value = store.share.seconds_left; notify('The door is open for five minutes. Add the house in the other app now.') }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}

/* Somebody scanning the code in another room reaches this screen the way everything else does -- the
   hub says something changed and the page asks what. The ticker is only the clock, and the slow poll
   under it is there for the one thing no message announces: a door running out of time by itself. */
watch(() => store.shareTick, refresh)
onMounted(() => {
  refresh()
  poll = window.setInterval(() => {
    tick.value++
    if (seconds.value != null && seconds.value > 0) seconds.value--
    if (share.value?.open && tick.value % 10 === 0) refresh()
  }, 1000)
})
onUnmounted(() => clearInterval(poll))
</script>

<template>
  <div class="page">
    <p class="page-lede">Your lights and plugs can appear in other apps as <b>Matter devices</b> &mdash; the standard Apple Home, Google Home and Alexa all speak. Turn this on and they show up there like any other accessory, ready for Siri, the Assistant or Alexa. Nothing goes out until you say so, and the house keeps working with all of them removed.</p>

    <!-- What the feature IS, drawn with this house's own things. The badge is OURS, not the Alliance's:
         the CSA's Matter mark may only go on a product they have certified, and this bridge is on a
         test vendor id. docs/matter.md, *Certification*. Swapping in the certified mark is this block. -->
    <div class="share-map" v-if="share?.ready">
      <div class="share-side">
        <span class="share-cap">{{ count }} {{ count === 1 ? 'thing' : 'things' }} {{ share.on ? 'shared' : 'here' }}</span>
        <span class="share-thing" v-for="t in preview" :key="t.name">
          <Icon :name="ICON[t.kind] ?? 'switch'" :size="15" />{{ t.name }}
        </span>
        <span class="share-note" v-if="more">…and {{ more }} more</span>
        <span class="share-note" v-else-if="!count">Nothing this bridge can carry yet</span>
      </div>

      <div class="share-mid">
        <span class="share-wire"></span>
        <span class="share-mark">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
            <path d="M12 9.2V5.4M12 13.6l-3.6 2.4M12 13.6l3.6 2.4" opacity=".9" />
            <circle cx="12" cy="11.4" r="2.2" fill="currentColor" stroke="none" />
            <circle cx="12" cy="4" r="1.9" fill="currentColor" stroke="none" />
            <circle cx="7.1" cy="17.2" r="1.9" fill="currentColor" stroke="none" />
            <circle cx="16.9" cy="17.2" r="1.9" fill="currentColor" stroke="none" />
          </svg>
        </span>
        <span class="share-word">Matter</span>
        <span class="share-note">your hub, speaking their language</span>
        <span class="share-wire out"></span>
      </div>

      <div class="share-side">
        <span class="share-cap">seen in</span>
        <span class="share-app" v-for="a in APPS" :key="a" :class="{ holding: holding(a) }">
          {{ a }}<span class="share-live" v-if="holding(a)" :title="`${a} has this house`"></span>
        </span>
        <span class="share-note">…and anything else that speaks Matter</span>
      </div>
    </div>

    <ul class="hub-rows" v-if="share">
      <!-- A hub whose installer predates sharing has no key for the bridge, and a switch that cannot
           work is worse than none: it says what to do instead. -->
      <li v-if="!share.ready">
        <span class="hub-k">Sharing</span>
        <span class="hub-v">This hub was set up before sharing existed, so it has no key for it yet.<span class="hub-sub line">Running the installer again adds one and changes nothing else.</span></span>
        <span></span>
      </li>

      <template v-else>
        <li>
          <span class="hub-k">Share</span>
          <span class="hub-v">{{ summary }}<span class="hub-sub line">Apple Home, Google Home and Alexa can see what you share, and ask their assistants for it. The house keeps working with all of them removed.</span></span>
          <button class="toggle" role="switch" :aria-checked="share.on" aria-label="Share this house" :class="{ on: share.on, busy: busy === 'on' }" @click="flip"><span class="knob"></span></button>
        </li>

        <template v-if="share.on">
          <li>
            <span class="hub-k">Apps</span>
            <span class="hub-v">
              <template v-if="held.length">{{ heldLine }}<span class="hub-sub line">A house can be held by several at once. Removing it is done in that app.</span></template>
              <template v-else-if="running">None yet.<span class="hub-sub line">Add the house in Apple Home, Google Home or Alexa, then scan the code.</span></template>
              <template v-else>None yet.<span class="hub-sub line">Nothing can be added while the part below is stopped.</span></template>
            </span>
            <button class="button small" :class="{ busy: busy === 'window' }" @click="addApp" v-if="!share.open && running">Add an app</button>
            <!-- The door is open. Where a window is running out there is a clock worth showing; where
                 nothing holds the house yet it is simply waiting to be scanned, and the row under this
                 one says the whole of that -- so this stays empty rather than saying "Open" twice. -->
            <span class="hub-sub" v-else-if="left">{{ left }} left</span>
            <span v-else></span>
          </li>

          <!-- The code, only while the door is open, and never a stale one: the hub stops answering
               for the picture the moment the window shuts. -->
          <li v-if="share.open" class="share-open">
            <span class="hub-k">Scan this</span>
            <span class="hub-v share-scan">
              <span class="phone-qr" v-if="!qrBroken"><img :src="shareQrUrl(tick >> 4)" alt="The code that adds this house to another app" width="132" height="132" @error="qrBroken = true" /></span>
              <span class="share-words">
                In the other app, choose to add a device or an accessory, then point it at this code.
                <b class="share-code" v-if="share.code">{{ share.code }}</b>
                <span class="hub-sub line">Type that number if the camera will not read the code. It works for five minutes, then the door shuts on its own.</span>
              </span>
            </span>
            <span></span>
          </li>

          <li>
            <span class="hub-k">What is shared</span>
            <span class="hub-v">
              <span class="share-kinds">
                <button v-for="k in share.offer" :key="k" class="chip-btn" :class="{ on: share.kinds.includes(k) }"
                        role="switch" :aria-checked="share.kinds.includes(k)" @click="flipKind(k)">{{ word(k).name }}</button>
              </span>
              <span class="hub-sub line">{{ kindsHint }}<template v-if="share.left_out_now"> {{ share.left_out_now }} {{ share.left_out_now === 1 ? 'thing is' : 'things are' }} kept home, set on {{ share.left_out_now === 1 ? 'its' : 'their' }} own page.</template></span>
            </span>
            <span></span>
          </li>

          <!-- Its own switch, and the sentence is the whole of the decision. Matter's door lock carries
               the unlock with the lock: there is no half to share, so this says what it means. -->
          <li>
            <span class="hub-k">Locks and garage doors</span>
            <span class="hub-v">{{ share.locks ? 'Shared.' : 'Not shared.' }}<span class="hub-sub line">If you share these, anything that can ask Siri, the Assistant or Alexa can unlock this door — including a voice outside it. Closing and locking cannot be shared on their own.</span></span>
            <button class="toggle" role="switch" :aria-checked="share.locks" aria-label="Share locks and garage doors" :class="{ on: share.locks, busy: busy === 'locks' }" @click="flipLocks"><span class="knob"></span></button>
          </li>

          <!-- Nothing is behind the page. Said plainly and where the button would have been, because the
               alternative -- which is what shipped -- is a button that answers "the door is open" and
               opens nothing. The house itself is unaffected, and that is the other half worth saying. -->
          <li v-if="stopped">
            <span class="hub-k">Not running</span>
            <span class="hub-v">The part of the hub that talks to other apps has stopped.<span class="hub-sub line">{{ held.length ? `${heldLine} still has this house, and nothing there will answer until it is back.` : 'Nothing can be added until it is back.' }} Your own lights and switches are unaffected.</span></span>
            <span></span>
          </li>

          <li v-if="share.bridge?.error">
            <span class="hub-k">Trouble</span>
            <span class="hub-v">{{ share.bridge.error }}<span class="hub-sub line">The house is unaffected; this is only what the other apps can see.</span></span>
            <span></span>
          </li>
        </template>
      </template>
    </ul>
  </div>
</template>

<style scoped>
/* Only this page has these. Everything else is panel.css's own hub-rows vocabulary, unchanged. */
.share-map {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(170px, 1fr);
  gap: 20px;
  align-items: center;
  padding: 22px 24px;
  margin-bottom: 26px;
  border-radius: 22px;
  background: var(--surface);
  border: 1px solid var(--edge);
}
.share-side {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}
.share-cap {
  font-size: 11.5px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 3px;
}
.share-thing,
.share-app {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  border-radius: 12px;
  background: var(--surface-hi);
  border: 1px solid var(--edge);
  font-size: 14px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.share-app.holding {
  border-color: rgba(116, 198, 157, 0.4);
}
.share-live {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--live);
  margin-left: auto;
  flex: none;
}
.share-note {
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.4;
}
.share-mid {
  display: grid;
  justify-items: center;
  gap: 2px;
}
.share-mark {
  width: 104px;
  height: 104px;
  border-radius: 32px;
  display: grid;
  place-items: center;
  background: linear-gradient(150deg, #f0c887, #dfa55c);
  color: var(--lamp-ink);
  box-shadow: 0 16px 38px -14px rgba(233, 184, 114, 0.45);
}
.share-word {
  font-size: 18px;
  font-weight: 600;
  margin-top: 11px;
}
/* The dashes either side. Decoration, so they go when the map stacks on a phone -- a line pointing
   sideways at nothing is worse than no line. */
.share-wire {
  display: none;
}
@media (min-width: 861px) {
  .share-mid {
    grid-template-columns: 56px auto 56px;
    /* The dashes belong on the badge's own row, not spanning all three: centred over mark+word+note
       they sit below the badge and read as two loose ticks rather than a wire into it. */
    grid-template-areas: "in mark out" ". word ." ". note .";
    align-items: center;
    column-gap: 16px;
  }
  .share-mark { grid-area: mark; }
  .share-word { grid-area: word; }
  .share-mid .share-note { grid-area: note; text-align: center; }
  .share-wire {
    display: block;
    grid-area: in;
    height: 0;
    border-top: 1.6px dashed rgba(233, 184, 114, 0.5);
    align-self: center;
    /* `justify-items: center` on the grid above shrinks every child to its content, and a rule with
       no content is nothing at all: without this the dashes are 0px wide and simply never appear. */
    justify-self: stretch;
  }
  .share-wire.out {
    grid-area: out;
    border-top-color: rgba(116, 198, 157, 0.5);
  }
}
@media (max-width: 860px) {
  .share-map {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}
.page-lede b {
  font-weight: 600;
  color: var(--ink);
}
.share-kinds {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.share-scan {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.share-words {
  flex: 1 1 220px;
}
.share-code {
  display: block;
  margin-top: 0.5em;
  font-size: 1.25em;
  font-weight: 600;
  letter-spacing: 0.06em;
}
</style>
