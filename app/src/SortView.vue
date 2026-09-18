<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { addRoom, moveDevice, renameDevice, forgetDevice, getSuggestions, type Device, type Room, type Suggestion } from './api'
import { store, cap, notify } from './store'
import { partWord, renameParts, unitsOf, type UnitRow } from './units'
import Icon from './Icon.vue'
import { pressedIn, snapshot, type Seen } from './pressed'

/* The "New devices" room: everything that has not been put in a room yet, each with a name to
   check and a room to pick. Once placed, a device leaves this list on its own. The same rows
   edit any other room (`editing`): rename a thing, or move it somewhere else.
   For new things the brain proposes a plain name and a room where it can (the house's own reasoning first,
   the assistant's after); a row shows its proposal with one Use button, and the bar above places them all.

   A ROW IS A UNIT, not a device (units.ts). A Brilliant dimmer or a Ring pathlight arrives as a light and
   a motion sensor on one piece of hardware, and this screen used to ask for their room twice with nothing
   on it to say the two were one thing. Now the unit is one row with its parts named under it; the room
   picked moves the hardware, which is what the brain did all along, and the name given is the unit's. */
const props = defineProps<{ room: Room; editing?: boolean }>()
defineEmits<{ back: [] }>()
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const rows = computed(() => unitsOf(props.room.devices))
const here = computed(() => props.editing ? props.room.id : '')
const names = ref<Record<string, string>>({})
const busy = ref<Record<string, string>>({})
const adding = ref<string | null>(null), newRoom = ref('')
const iconFor = (d: Device) => cap(d) === 'media' && /\b(tv|television|roku)\b/i.test(d.name) ? 'tv' : cap(d)
const roomName = (id: string) => store.rooms.find(r => r.id === id)?.name ?? 'room'
const isUnit = (r: UnitRow) => r.parts.length > 1
const partsLine = (r: UnitRow) => r.parts.map(d => partWord(d, r.name)).join(' · ')
/* the placed unit leaves the list at once; the house confirms with a rebuild, and waiting for the round trip would leave it sitting there */
function gone(r: UnitRow) {
  const ids = new Set(r.parts.map(d => d.id))
  // eslint-disable-next-line vue/no-mutating-props
  props.room.devices = props.room.devices.filter(x => !ids.has(x.id))
}

async function renameTo(r: UnitRow, n: string) {
  if (isUnit(r)) { await renameDevice(r.lead.id, n, true); renameParts(r.parts, r.name, n) }
  else { await renameDevice(r.lead.id, n); r.lead.name = n }
}
async function rename(r: UnitRow) {
  const n = (names.value[r.key] ?? r.name).trim()
  if (!n || n === r.name) return
  busy.value[r.key] = 'name'
  try { await renameTo(r, n); notify(`Renamed to ${n}.`) } catch (e: any) { notify(`Couldn't rename: ${e.message}`, 'error') }
  delete busy.value[r.key]
}
async function move(r: UnitRow, roomId: string) {
  if (roomId === '__new') { adding.value = r.key; newRoom.value = ''; return }
  busy.value[r.key] = 'room'
  try {
    await moveDevice(r.lead.id, roomId)
    notify(`${r.name} is in the ${roomName(roomId)} now.`)
    gone(r)
  } catch (e: any) { notify(`Couldn't move it: ${e.message}`, 'error') }
  delete busy.value[r.key]
}
/* The end of a thing's life here. One tap asks with the name in it, so what disappears is said before it
   does; the second does it. Not offered on New devices, where a thing that is forgotten is only rediscovered. */
const forgetting = ref('')
async function forget(r: UnitRow) {
  if (forgetting.value !== r.key) { forgetting.value = r.key; return }
  busy.value[r.key] = 'forget'
  try {
    await forgetDevice(r.lead.id)
    notify(`${r.name} is forgotten.`)
    gone(r)
  } catch (e: any) { notify(e.message, 'error') }
  forgetting.value = ''
  delete busy.value[r.key]
}
async function createAndMove(r: UnitRow) {
  const n = newRoom.value.trim(); if (!n) { adding.value = null; return }
  busy.value[r.key] = 'room'
  try { const rm = await addRoom(n); store.rooms.push({ id: rm.id, name: rm.name, devices: [], intent: 'unknown' }); adding.value = null; await move(r, rm.id) }
  catch (e: any) { notify(`Couldn't add the room: ${e.message}`, 'error'); delete busy.value[r.key] }
}

/* ---------- naming by touch ----------

   Eleven identical rows called "Switch 000a" is the failure this exists to stop. A switch on a wall
   announces itself the moment a human presses it -- that is how the house reads its state at all --
   so the way to tell the rows apart is to go and press one, and the row it belongs to says so.

   In place, never at the top. A row that jumped would move under the finger of somebody already
   reaching for it, and a second tap in the same place would reach a different thing; the room grid
   learned that the hard way. It highlights where it is and scrolls itself into view.

   Nothing here is new machinery: it reads the same event log the why-sheet reads. The only events
   that count are state changes on things in THIS list, recent, and not ones this screen caused --
   a rename or a move makes no state event, so a press is the only thing left.

   The press is a device's (a state is a device's), and the row it lights is the UNIT's: a dimmer and
   the motion sensor on the same piece of hardware are one row, and a press on the switch lights that
   row, motion sensor and all. */
const PRESS_FOR = 45000
const pressed = ref<{ id: string; at: number } | null>(null)
const now = ref(Date.now())
const rowOf = (id: string) => rows.value.find(r => r.parts.some(d => d.id === id))?.key ?? id
const live = computed(() => pressed.value && now.value - pressed.value.at < PRESS_FOR ? rowOf(pressed.value.id) : null)
/* Only things that can announce themselves: a wall switch does, a bulb behind a bridge does, a camera
   does not. Saying "go and press one" over a list of things that cannot answer would be a lie. */
const CAN_PRESS = ['light', 'switch', 'cover', 'lock']
const pressable = computed(() => props.room.devices.filter(d => CAN_PRESS.includes(cap(d))))
const teach = computed(() => !props.editing && rows.value.filter(r => CAN_PRESS.includes(cap(r.lead))).length > 1)
/* The press itself, in pressed.ts -- and it is the only thing this screen watches. */
let seen: Seen = {}
watch(() => props.room.devices.map(d => `${d.id}:${d.state}`).join(), () => {
  const was = seen
  seen = snapshot(props.room.devices)
  const hit = pressedIn(was, pressable.value, id => !!busy.value[rowOf(id)])
  if (!hit) return
  pressed.value = { id: hit, at: Date.now() }
  now.value = Date.now()
  setTimeout(() => document.querySelector('.sort-row.pressed')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 30)
}, { immediate: true })
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(tick))
/* what a pressed thing turned out to be, in its own words rather than its address: the lead part says
   what it is, and a motion sensor among the parts is said with it */
function what(u: UnitRow) {
  const d = u.lead, c = cap(d), bits: string[] = []
  if (c === 'light') bits.push(d.attrs?.brightness != null ? 'A light that dims' : 'A light')
  else if (c === 'switch') bits.push('A switch')
  else if (c === 'lock') bits.push('A lock')
  else if (c === 'cover') bits.push('A blind')
  if (u.parts.some(p => cap(p) === 'motion') || d.attrs?.has_motion || /motion/i.test(d.name)) bits.push('with a motion sensor in it')
  return bits.join(', ') + '.'
}

/* what the brain proposes for each new thing; a unit takes its lead part's proposal, and the brain's own
   reasoning already reads the parts together (suggest.py puts a unit's siblings in the words it looks at) */
const suggestions = ref<Record<string, Suggestion>>({})
const sug = (r: UnitRow) => suggestions.value[r.lead.id]
const thinking = ref(false), applying = ref(false)
const placeable = computed(() => rows.value.filter(r => sug(r)?.room).length)
async function think() {
  if (props.editing || !props.room.devices.length) return
  thinking.value = true
  try { const s = await getSuggestions(); const by: Record<string, Suggestion> = {}; for (const i of s.items) by[i.id] = i; suggestions.value = by } catch {}
  thinking.value = false
}
async function use(r: UnitRow): Promise<boolean> {
  const s = sug(r); if (!s || busy.value[r.key]) return false
  busy.value[r.key] = 'room'
  try {
    if (s.name && s.name !== r.name) { await renameTo(r, s.name); names.value[r.key] = s.name }
    if (s.room) { await moveDevice(r.lead.id, s.room); gone(r); notify(`${s.name} is in the ${roomName(s.room)} now.`) }
    else notify(`Renamed to ${s.name}.`)
    delete suggestions.value[r.lead.id]
  } catch (e: any) { notify(`Couldn't place it: ${e.message}`, 'error'); delete busy.value[r.key]; return false }
  delete busy.value[r.key]
  return true
}
async function useAll() {
  if (applying.value) return
  applying.value = true
  for (const r of [...rows.value]) if (sug(r)?.room && !(await use(r))) break   // the first refusal (a wrong code, the engine away) stops the run
  applying.value = false
}
onMounted(think)
watch(() => props.room.devices.length, (n, was) => { if (n > (was ?? 0)) think() })   // something new arrived: look again
</script>

<template>
  <section class="room">
    <header class="stage-head room-head">
      <button class="back" @click="$emit('back')" :aria-label="editing ? 'Done' : 'Back to home'"><Icon :name="editing ? 'check' : 'back'" :size="22" /></button>
      <div>
        <h1 class="display">{{ editing ? room.name : 'New devices' }}</h1>
        <p class="lede">{{ editing ? 'Rename anything, move it to another room, or forget it for good. Tap the tick when you are done.' : 'Check each name and say which room it lives in. It moves there on its own.' }}</p>
      </div>
    </header>

    <!-- The scroll starts here and not at the stage: the head above it -- the way back with it --
         must never travel, while everything below it has to be reachable on a panel of any height.
         The teaching bars are inside it because they are not the way back: on a short wall they
         scroll away and give the rows the screen, rather than standing over a window too small to
         hold a single row. -->
    <div class="sort-scroll">
      <!-- how to tell them apart at all. Drawn from design/puck/Naming.dc.html. -->
      <div class="press-bar" v-if="teach">
        <span class="press-icon"><Icon name="switch" :size="20" /></span>
        <span class="press-text">
          <span class="press-name">Go and press one</span>
          <span class="press-sub">Top or bottom, it does not matter — the one you press says so here. Nothing will switch on that was not going to.</span>
        </span>
      </div>

      <div class="suggest-bar" v-if="!editing && room.devices.length && (thinking || placeable)">
        <span class="suggest-lede"><Icon name="sparkle" :size="16" /><span>{{ thinking ? 'Working out where these go…' : placeable === 1 ? 'One of these looks like it has a home. Check it and tap Use.' : `${placeable} of these look like they have a home. Check them, or place them all.` }}</span></span>
        <button class="button small" v-if="placeable > 1" :class="{ busy: applying }" @click="useAll">Place all {{ placeable }}</button>
      </div>

      <ul class="sort" v-if="room.devices.length">
        <li v-for="u in rows" :key="u.key" class="sort-row" :class="{ busy: busy[u.key], unit: isUnit(u), pressed: live === u.key }">
          <span class="sort-icon"><Icon :name="iconFor(u.lead)" :size="20" /></span>
          <div class="sort-main">
            <!-- on the pressed card the name is asked below, in words, so the header shows it and does not ask twice -->
            <span class="sort-name still" v-if="live === u.key && !editing">{{ names[u.key] ?? u.name }}</span>
            <input v-else class="sort-name" :value="names[u.key] ?? u.name" @input="names[u.key] = ($event.target as HTMLInputElement).value" @change="rename(u)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" aria-label="Name" />
            <!-- one thing on the wall with more than one part in it: say what the parts are, so nobody has to guess which sensor is which switch's -->
            <span class="sort-parts" v-if="isUnit(u)"><Icon name="motion" :size="13" v-if="u.parts.some(d => cap(d) === 'motion')" />{{ partsLine(u) }}</span>
          </div>
          <template v-if="adding === u.key">
            <input class="sort-name" v-model="newRoom" placeholder="Name the room" autofocus @keydown.enter="createAndMove(u)" @keydown.escape="adding = null" />
            <button class="button small" @click="createAndMove(u)">Add</button>
          </template>
          <select v-else-if="live !== u.key || editing" class="sort-room" :value="here" @change="move(u, ($event.target as HTMLSelectElement).value)" aria-label="Room">
            <option value="" disabled>Which room?</option>
            <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
            <option value="__new">A new room…</option>
          </select>
          <button v-if="editing && adding !== u.key" class="button small ghost sort-forget" :class="{ warn: forgetting === u.key }" @click="forget(u)">{{ forgetting === u.key ? 'Forget?' : 'Forget' }}</button>
          <p class="sort-forget-ask" v-if="forgetting === u.key"><b>{{ u.name }}</b>{{ isUnit(u) ? ', all of it,' : '' }} goes from the house, and from whatever brought it. Tap again to do it.</p>
          <!-- the one that was just pressed: the rooms as chips, because the answer is one tap away
               and a dropdown would hide it behind two -->
          <div class="press-line" v-if="live === u.key && !editing">
            <!-- "you pressed" and not "it came on": the house knows the switch reported a change because a hand
                 was on it, and nothing more. A stairway's companion switch has no load wired to it at all, and
                 there is no way yet to tell one from the mesh -- so the row says what is true of both. -->
            <span class="press-said"><span class="pulse-dot"></span>You just pressed this one. {{ what(u) }}</span>
            <!-- the name, asked in words at the one moment the person knows what the thing is. The same
                 field as the row's own (it saves when you leave it); the brain's suggestion fills it in. -->
            <label class="press-name">
              <span class="field-label">Call it</span>
              <input class="input" :value="names[u.key] ?? sug(u)?.name ?? u.name" @input="names[u.key] = ($event.target as HTMLInputElement).value" @change="rename(u)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" autocapitalize="words" aria-label="Name" />
            </label>
            <span class="field-label">Which room is it in?</span>
            <div class="press-rooms">
              <button v-for="r in rooms" :key="r.id" class="chip-btn" @click="move(u, r.id)">{{ r.name }}</button>
              <button class="chip-btn ghost" @click="move(u, '__new')">Another room…</button>
            </div>
          </div>
          <div class="suggest-line" v-if="!editing && sug(u)">
            <Icon name="sparkle" :size="14" />
            <span>Looks like <b>{{ sug(u).name }}</b><template v-if="sug(u).room"> in the <b>{{ roomName(sug(u).room) }}</b></template><span class="suggest-why" v-if="sug(u).why"> · {{ sug(u).why }}</span></span>
            <button class="button small" @click="use(u)">Use</button>
          </div>
        </li>
      </ul>
      <div v-else class="empty-room">
        <p class="empty">{{ editing ? 'Nothing left in this room.' : 'Everything has a room.' }}</p>
        <p class="empty-sub">{{ editing ? 'Everything moved elsewhere. Tap the tick to go back.' : 'Anything you add later that does not know where it lives will wait here.' }}</p>
      </div>
    </div>
  </section>
</template>
