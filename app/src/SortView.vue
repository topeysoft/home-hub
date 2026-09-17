<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { addRoom, moveDevice, renameDevice, forgetDevice, getSuggestions, type Device, type Room, type Suggestion } from './api'
import { store, cap, notify } from './store'
import { partWord, renameParts, unitsOf, type UnitRow } from './units'
import Icon from './Icon.vue'

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

    <div class="suggest-bar" v-if="!editing && room.devices.length && (thinking || placeable)">
      <span class="suggest-lede"><Icon name="sparkle" :size="16" /><span>{{ thinking ? 'Working out where these go…' : placeable === 1 ? 'One of these looks like it has a home. Check it and tap Use.' : `${placeable} of these look like they have a home. Check them, or place them all.` }}</span></span>
      <button class="button small" v-if="placeable > 1" :class="{ busy: applying }" @click="useAll">Place all {{ placeable }}</button>
    </div>

    <ul class="sort" v-if="room.devices.length">
      <li v-for="u in rows" :key="u.key" class="sort-row" :class="{ busy: busy[u.key], unit: isUnit(u) }">
        <span class="sort-icon"><Icon :name="iconFor(u.lead)" :size="20" /></span>
        <div class="sort-main">
          <input class="sort-name" :value="names[u.key] ?? u.name" @input="names[u.key] = ($event.target as HTMLInputElement).value" @change="rename(u)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" aria-label="Name" />
          <!-- one thing on the wall with more than one part in it: say what the parts are, so nobody has to guess which sensor is which switch's -->
          <span class="sort-parts" v-if="isUnit(u)"><Icon name="motion" :size="13" v-if="u.parts.some(d => cap(d) === 'motion')" />{{ partsLine(u) }}</span>
        </div>
        <template v-if="adding === u.key">
          <input class="sort-name" v-model="newRoom" placeholder="Name the room" autofocus @keydown.enter="createAndMove(u)" @keydown.escape="adding = null" />
          <button class="button small" @click="createAndMove(u)">Add</button>
        </template>
        <select v-else class="sort-room" :value="here" @change="move(u, ($event.target as HTMLSelectElement).value)" aria-label="Room">
          <option value="" disabled>Which room?</option>
          <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
          <option value="__new">A new room…</option>
        </select>
        <button v-if="editing && adding !== u.key" class="button small ghost sort-forget" :class="{ warn: forgetting === u.key }" @click="forget(u)">{{ forgetting === u.key ? 'Forget?' : 'Forget' }}</button>
        <p class="sort-forget-ask" v-if="forgetting === u.key"><b>{{ u.name }}</b>{{ isUnit(u) ? ', all of it,' : '' }} goes from the house, and from whatever brought it. Tap again to do it.</p>
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
  </section>
</template>
