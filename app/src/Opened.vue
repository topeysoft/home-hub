<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * One device, opened in place.
 *
 * The home does not get covered, it recedes: scaled back, blurred and dimmed,
 * so the panel reads as something in front of the house rather than a new page.
 * The timings are measured, not invented — 320ms for the home to fall back,
 * 380ms for the panel to rise, and the content comes up behind it in four beats.
 *
 * Those are paper's. Glass has a measured set of its own, and a room that dims
 * rather than blurring — all of it in panel.css under [data-face='glass'], none
 * of it here, because a face gets to change how a thing moves and not what it
 * is. The one exception is `closing` below, which exists because CSS cannot see
 * the difference between a pane that has not risen yet and one on its way out.
 *
 * The field takes the device's own color while it is open: a warm lamp pushes
 * the whole room amber, a camera cools it.
 *
 * WHAT THIS PANE IS, since it used to be one layout for everything. Six slots,
 * and only the fifth changes from a lamp to a mower:
 *
 *   1  where and what      the room, then the name -- and under it, quietly, what
 *                          the house is showing this as when its owner has
 *                          disagreed with the driver (docs/kinds.md)
 *   2  what you can do     the kind's real verbs -- never a blanket power
 *                          button, which for a lock, a blind, a camera and a
 *                          mower was an action the brain refuses with a 400
 *   3  what it says        one reading, large
 *   4  why it is like that one line, then the facts this thing actually knows
 *   5  the instrument      the control a tile is too small for. This is the
 *                          half of the pane that used to hold a 260px
 *                          watermark of the device's own icon and nothing else
 *   6  what it did today   /events, narrowed to this one device
 *
 * See design/device for the boards all of that was drawn on.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getDeviceEvents, getDeviceKinds, moveDevice, renameDevice, setDeviceKind, setDeviceLead, setDeviceShared, type Event, type Kinds } from './api'
import { partnerOf, partsOf, renameParts, renamesUnit } from './units'
import { isMachine } from './machines'
import MachinePane from './panes/MachinePane.vue'
import { canShare, cap, defaultKind, deviceById, isDead, isShared, notify, perform, roomOf, shownAs, store } from './store'
import { facts as factsOf, moments as momentsOf, paneKind, reading, verbs as verbsOf, whyLine } from './pane'
import { useArm } from './twice'
import Icon from './Icon.vue'
import LightPane from './panes/LightPane.vue'
import MediaPane from './panes/MediaPane.vue'
import ClimatePane from './panes/ClimatePane.vue'
import CoverPane from './panes/CoverPane.vue'
import LockPane from './panes/LockPane.vue'
import CameraPane from './panes/CameraPane.vue'
import SimplePane from './panes/SimplePane.vue'
import SensePane from './panes/SensePane.vue'

const dev = computed(() => store.opened)
const kind = computed(() => dev.value ? cap(dev.value) : '')
const room = computed(() => dev.value ? roomOf(dev.value) : null)
const shown = ref(false)              // flipped a frame after mount, so the transitions have a from-state to leave from
const dead = computed(() => !!dev.value && isDead(dev.value))

const INSTRUMENTS: Record<string, any> = {
  light: LightPane, media: MediaPane, climate: ClimatePane, cover: CoverPane,
  lock: LockPane, camera: CameraPane, fan: SimplePane, switch: SimplePane, alarm: SimplePane, appliance: SimplePane, vacuum: SimplePane, sense: SensePane, machine: MachinePane,
}
const instrument = computed(() => dev.value ? INSTRUMENTS[paneKind(dev.value)] ?? SimplePane : null)

/* what this one thing has done, from the log the brain already keeps. Asked for once on the way in
   and again whenever the thing itself changes, which is the only time there is anything new. */
const events = ref<Event[]>([])
async function look() {
  const d = dev.value; if (!d) return
  /* a machine's day is its features' days, together: the brain has no record under the machine's own name */
  const ids = isMachine(d) ? (d.attrs.parts as string[]) : [d.id]
  try {
    const all = await Promise.all(ids.map(id => getDeviceEvents(id, 12).catch(() => [] as Event[])))
    events.value = all.flat().sort((a, b) => b.ts - a.ts).slice(0, 12)
  } catch { events.value = [] }
}
watch(() => dev.value?.id, look, { immediate: true })
watch(() => [dev.value?.state, JSON.stringify(dev.value?.attrs ?? {})].join('|'), () => { if (dev.value) look() })

/* ---------- what it is, when the house has it wrong ----------
   A lamp on a smart plug is a switch to the driver and a light to everybody who lives there, and until
   somebody can say so from here the only way to fix it is to leave the panel and edit an entity in Home
   Assistant -- the one move the whole box is shaped to avoid. So it sits under the name, because that is
   where somebody already is when they notice.

   What may be offered is the brain's to decide, not this file's: it is computed from what the device can
   already serve, which is what stops a brightness slider being drawn onto something that cannot dim. An
   offer of fewer than two is no choice at all, and nothing is drawn. */
const kinds = ref<Kinds | null>(null)
const picking = ref(false)
const offer = computed(() => kinds.value && kinds.value.offer.length > 1 ? kinds.value : null)
const said = computed(() => dev.value ? shownAs(dev.value) : '')

/* Kept out of the other apps, or not. On the device's own pane and nowhere else, for the reason
   *Show this as* is here: a person decides this standing in front of the lamp, and the Share page
   would otherwise have to draw a row per light, which is the list it exists to avoid. */
const shareable = computed(() => !!dev.value && canShare(dev.value))
const shared = computed(() => !!dev.value && isShared(dev.value))
const sharing = ref(false)
async function shareIt(next: boolean) {
  const d = dev.value
  if (!d || sharing.value || next === shared.value) return
  sharing.value = true
  try { store.share = await setDeviceShared(d.id, next) }
  catch (e: any) { notify(e.message, 'error') }
  sharing.value = false
}
watch(() => dev.value?.id, async id => {
  kinds.value = null; picking.value = false
  if (!id || (dev.value && isMachine(dev.value))) return     // a machine is not a thing to re-type; its features are, each on its own page
  try { const k = await getDeviceKinds(id); if (dev.value?.id === id) kinds.value = k } catch { kinds.value = null }
}, { immediate: true })

/* The row stays open behind the choice, and the choice stays where the finger left it: what you just
   touched is the way back out of it. The pane re-draws at once rather than waiting for the brain to say
   so -- the same guess every other control on this panel makes -- and puts itself back if it was wrong. */
async function showAs(k: string) {
  const d = dev.value; if (!d || !kinds.value) return
  if (k === kinds.value.kind) return
  const was = d.kind
  d.kind = k === defaultKind(d) ? null : k     // the way back is what it would be shown as anyway, which for a fridge's switch is the house's guess
  kinds.value = { ...kinds.value, kind: k }
  try { await setDeviceKind(d.id, k) }
  catch (e: any) {
    d.kind = was
    kinds.value = { ...kinds.value, kind: was || defaultKind(d) }
    notify(e.message, 'error')
  }
}

/* The verb row asks twice about the same two things the tile does, and says so in the one place on
   this pane that is already words: the reading. A row of icon-only buttons cannot wear a sentence,
   and a dialogue over the top of the pane would be the "Are you sure?" health.py rules out. */
const { armed, tap: armedTap, clear: disarm } = useArm()
watch(() => dev.value?.id, () => disarm())
const big = computed(() => armed.value || (dev.value ? reading(dev.value, store.tempUnit) : ''))
const facts = computed(() => dev.value ? factsOf(dev.value, room.value, store.tempUnit, events.value) : [])
const verbs = computed(() => dev.value ? verbsOf(dev.value) : [])
const moments = computed(() => dev.value ? momentsOf(events.value, dev.value, 4, Date.now(), store.tempUnit) : [])
const why = computed(() => dev.value ? whyLine(dev.value, events.value, room.value, Date.now(), store.tempUnit) : '')

async function verb(id: string) {
  const d = dev.value; if (!d) return
  if (id === 'why') { store.whyRoom = d.room_id; store.sheet = 'why'; return }
  if (id === 'edit') { startEdit(); return }
  if (id === 'watch') { store.viewer = d; close(); return }
  if (id === 'lamp' || id === 'fan') {
    const other = deviceById(String(id === 'lamp' ? d.attrs.light : d.attrs.fan))
    if (other) await perform(other, other.state === 'on' ? 'off' : 'on', undefined, { state: other.state === 'on' ? 'off' : 'on' })
    return
  }
  if (id === 'power') {
    if (dead.value) return
    const on = d.state === 'on' || d.state === 'playing' || (cap(d) === 'climate' && d.state !== 'off')
    armedTap(cap(d), on ? 'off' : 'on', async () => {
      try { await perform(d, on ? 'off' : 'on', undefined, { state: on ? 'off' : 'on' }) }
      catch (e: any) { notify(e.message, 'error') }
    })
  }
}

/* A fan with a light in it: which part is the tile. Fan by default -- it is the thing on the ceiling and
   the light is a part of it -- and the owner may say the light instead, from either part's pane, if that
   is the half they reach for. The brain keeps it with the kinds (docs/units.md). */
const partner = computed(() => dev.value ? partnerOf(dev.value) : undefined)
const leads = computed(() => (dev.value?.attrs.leads as 'fan' | 'light' | undefined) ?? 'fan')
async function leadWith(k: 'fan' | 'light') {
  const d = dev.value, p = partner.value; if (!d || !p || k === leads.value) return
  const was = leads.value
  d.attrs.leads = k; p.attrs.leads = k
  try { await setDeviceLead(d.id, k) }
  catch (e: any) { d.attrs.leads = was; p.attrs.leads = was; notify(e.message, 'error') }
}

/* Rename or move it, HERE. The verb used to open the house's settings panel, which has no rename in it --
   a promise the button made and the panel broke. The name and the room are the two things a person can see
   and disagree with (the kind is the third, above), so they are edited where they are read: the head of
   the pane turns into a name field and a room picker, and Done puts it back.

   A light called "Walkway Pathlight Light" on hardware called "Walkway Pathlight" is the unit, so renaming
   it renames the unit and its parts follow (units.ts). A fridge's "Ice Maker" is a feature: only itself. */
const editing = ref(false), saving = ref(false)
const newName = ref(''), newRoom = ref('')
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const asUnit = computed(() => !!dev.value && (isMachine(dev.value) || renamesUnit(dev.value)))   // a machine IS its unit: the fridge's name is the hardware's
function startEdit() {
  const d = dev.value; if (!d) return
  newName.value = asUnit.value ? (d.hw_name ?? d.name) : d.name
  newRoom.value = d.room_id === 'unassigned' ? '' : d.room_id
  editing.value = true
}
watch(() => dev.value?.id, () => (editing.value = false))
async function saveEdit() {
  const d = dev.value; if (!d || saving.value) return
  const name = newName.value.trim(), was = asUnit.value ? (d.hw_name ?? d.name) : d.name
  const room = newRoom.value
  saving.value = true
  try {
    /* a machine has no id the brain knows: its first feature stands for it, and the brain renames and
       moves the hardware through that one, which carries the rest */
    const through = isMachine(d) ? partsOf(d)[0] ?? d : d
    if (name && name !== was) {
      if (asUnit.value) { await renameDevice(through.id, name, true); renameParts(partsOf(d), was, name); if (isMachine(d)) { d.name = name; d.hw_name = name } }
      else { await renameDevice(d.id, name); d.name = name }
    }
    if (room && room !== d.room_id) {
      await moveDevice(through.id, room)
      if (isMachine(d)) d.room_id = room
      /* the thing goes now, its parts with it; the house confirms with a rebuild */
      for (const part of partsOf(d)) {
        const from = store.rooms.find(r => r.id === part.room_id), to = store.rooms.find(r => r.id === room)
        if (from && to && from !== to) { from.devices = from.devices.filter(x => x.id !== part.id); to.devices.push(part); part.room_id = room }
      }
    }
    if ((name && name !== was) || (room && room !== d.room_id)) notify(name !== was && room !== d.room_id ? `${name} is in the ${rooms.value.find(r => r.id === room)?.name ?? 'room'} now.` : name !== was ? `Renamed to ${name}.` : `${d.name} is in the ${rooms.value.find(r => r.id === room)?.name ?? 'room'} now.`)
    editing.value = false
  } catch (e: any) { notify(`Couldn't change it: ${e.message}`, 'error') }
  saving.value = false
}

/* `closing` is not the same fact as `!shown`, and the difference is two frames:
   between mounting and the rise beginning, the pane is also not shown, and CSS
   cannot tell those two apart. Something has to, because the bottom bar's way
   back is counted from the moment the fall STARTS -- see panel.css. The
   timeout is a frame past the longest fall either face has, paper's 280ms and
   glass's 300, so the last of the slide is never clipped. */
const closing = ref(false)
function close() { shown.value = false; closing.value = true; setTimeout(() => (store.opened = null), 320) }

function onKey(e: KeyboardEvent) { if (e.key === 'Escape') close() }
/* Two frames, not one. onMounted runs before the browser has painted anything,
   and a single requestAnimationFrame still lands inside the frame that paints
   the panel for the first time -- so `shown` was already on by that first paint
   and there was nothing to transition from: the panel simply appeared. The
   second frame is the one that gets painted down at translateY(100%), and the
   rise begins from there. Closing never had the problem, which is why it was
   only ever wrong in one direction. */
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="opened" :class="{ shown, closing }" v-if="dev" role="dialog" :aria-label="dev.name">
    <div class="opened-veil" @click="close"></div>
    <div class="opened-panel" :data-cap="kind">
      <button class="back opened-close" @click="close" aria-label="Close"><Icon name="close" :size="18" /></button>

      <div class="opened-body pane-body">
        <div class="pane-said">
          <div class="opened-step s0">
            <template v-if="!editing">
              <div class="opened-room" v-if="room">{{ room.name }}</div>
              <h2 class="display opened-name">{{ dev.name }}</h2>
            </template>
            <!-- the same two lines, as things to change: the room, then the name -->
            <form class="opened-edit" v-else @submit.prevent="saveEdit">
              <select class="sort-room opened-edit-room" v-model="newRoom" aria-label="Room">
                <option value="" disabled>Which room?</option>
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
              </select>
              <input class="opened-edit-name" v-model="newName" spellcheck="false" aria-label="Name" autofocus @keydown.escape="editing = false" />
              <p class="opened-edit-note" v-if="asUnit">The whole unit takes this name: {{ partsOf(dev).length }} parts, its motion sensor among them.</p>
              <div class="opened-edit-acts">
                <button type="submit" class="button small" :disabled="saving || !newName.trim()">Done</button>
                <button type="button" class="button small ghost" :disabled="saving" @click="editing = false">Cancel</button>
              </div>
            </form>

            <!-- what it is. Quiet, and only ever here: a tile is a glance, and the point of the
                 override is that the thing stops looking unusual. -->
            <div class="opened-kind" v-if="offer">
              <button class="opened-kind-say" :aria-expanded="picking" @click="picking = !picking">
                {{ said || 'Show this as' }}
              </button>
              <div class="opened-kind-pick" v-if="picking">
                <div class="opened-kind-row">
                  <button v-for="k in offer.offer" :key="k" class="opened-kind-one" :class="{ on: k === offer.kind }"
                          :aria-pressed="k === offer.kind" @click="showAs(k)">{{ offer.words[k] }}</button>
                </div>
                <p class="opened-kind-why">{{ offer.why }}</p>
              </div>
            </div>
            <!-- whether the other apps can see this one. Only where the house is sharing this kind at
                 all: a switch that cannot mean anything is worse than no switch. docs/matter.md. -->
            <div class="opened-kind opened-share" v-if="shareable">
              <span class="opened-kind-say still">{{ shared ? 'Shared with other apps' : 'Kept out of other apps' }}</span>
              <div class="opened-kind-pick">
                <div class="opened-kind-row">
                  <button class="opened-kind-one" :class="{ on: shared, busy: sharing }" :aria-pressed="shared" @click="shareIt(true)">Shared</button>
                  <button class="opened-kind-one" :class="{ on: !shared, busy: sharing }" :aria-pressed="!shared" @click="shareIt(false)">Kept home</button>
                </div>
                <p class="opened-kind-why">{{ shared ? 'Apple Home, Google Home and Alexa can see this one and ask their assistants for it.' : 'The rest of its kind still goes out; this one stays in the house.' }}</p>
              </div>
            </div>
            <!-- a fan with a light in it: which of the two is the tile. The same quiet row as the kind. -->
            <div class="opened-kind opened-lead" v-if="partner">
              <span class="opened-kind-say still">Lead with</span>
              <div class="opened-kind-pick">
                <div class="opened-kind-row">
                  <button class="opened-kind-one" :class="{ on: leads === 'fan' }" :aria-pressed="leads === 'fan'" @click="leadWith('fan')">Fan</button>
                  <button class="opened-kind-one" :class="{ on: leads === 'light' }" :aria-pressed="leads === 'light'" @click="leadWith('light')">Light</button>
                </div>
                <p class="opened-kind-why">One tile for the fan and its light. The one leading is the tile; the other is a row on it.</p>
              </div>
            </div>
          </div>

          <div class="opened-step s1 opened-acts">
            <button v-for="v in verbs" :key="v.id" class="ctl" :class="{ primary: v.primary, off: v.primary && !v.on, lit: !v.primary && v.on }"
                    :disabled="dead && v.id === 'power'" :aria-label="v.label" :title="v.label" @click="verb(v.id)">
              <Icon :name="v.icon" :size="v.primary ? 22 : 20" />
            </button>
          </div>

          <div class="opened-step s2">
            <div class="opened-big display" :class="{ absent: dead }">{{ big }}</div>
            <p class="pane-why" v-if="why">{{ why }}</p>
          </div>

        </div>

        <!-- the facts sit under what was said on a wall, and under the INSTRUMENT on a phone, where
             the control has to be reachable without scrolling past four numbers to get to it -->
        <div class="opened-step s3 opened-facts pane-facts" v-if="facts.length">
          <div v-for="f in facts" :key="f.k">
            <div class="opened-fact-v">{{ f.v }}</div>
            <div class="opened-fact-k">{{ f.k }}</div>
          </div>
        </div>

        <!-- the instrument: the control a tile is too small for -->
        <div class="pane-rig" v-if="instrument">
          <component :is="instrument" :device="dev" :events="events" :moments="moments" />
        </div>
      </div>

      <!-- what this one thing did today -->
      <div class="opened-step s3 pane-day" v-if="moments.length">
        <span class="opened-fact-k pane-day-head">Today</span>
        <div class="pane-day-row">
          <div v-for="(m, i) in moments" :key="i" class="pane-moment">
            <div class="pane-moment-t">{{ m.when }}</div>
            <div class="pane-moment-x">{{ m.text }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
