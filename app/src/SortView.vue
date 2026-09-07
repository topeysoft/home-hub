<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { addRoom, moveDevice, renameDevice, getSuggestions, type Device, type Room, type Suggestion } from './api'
import { store, cap, notify } from './store'
import Icon from './Icon.vue'

/* The "New devices" room: everything that has not been put in a room yet, each with a name to
   check and a room to pick. Once placed, a device leaves this list on its own. The same rows
   edit any other room (`editing`): rename a thing, or move it somewhere else.
   For new things the brain proposes a plain name and a room where it can (the house's own reasoning first,
   the assistant's after); a row shows its proposal with one Use button, and the bar above places them all. */
const props = defineProps<{ room: Room; editing?: boolean }>()
defineEmits<{ back: [] }>()
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const here = computed(() => props.editing ? props.room.id : '')
const names = ref<Record<string, string>>({})
const busy = ref<Record<string, string>>({})
const adding = ref<string | null>(null), newRoom = ref('')
const iconFor = (d: Device) => cap(d) === 'media' && /\b(tv|television|roku)\b/i.test(d.name) ? 'tv' : cap(d)
const roomName = (id: string) => store.rooms.find(r => r.id === id)?.name ?? 'room'

async function rename(d: Device) {
  const n = (names.value[d.id] ?? d.name).trim()
  if (!n || n === d.name) return
  busy.value[d.id] = 'name'
  try { await renameDevice(d.id, n); d.name = n; notify(`Renamed to ${n}.`) } catch (e: any) { notify(`Couldn't rename: ${e.message}`, 'error') }
  delete busy.value[d.id]
}
async function move(d: Device, roomId: string) {
  if (roomId === '__new') { adding.value = d.id; newRoom.value = ''; return }
  busy.value[d.id] = 'room'
  try {
    await moveDevice(d.id, roomId)
    notify(`${d.name} is in the ${roomName(roomId)} now.`)
    props.room.devices = props.room.devices.filter(x => x.id !== d.id)   // the house will confirm with a rebuild
  } catch (e: any) { notify(`Couldn't move it: ${e.message}`, 'error') }
  delete busy.value[d.id]
}
async function createAndMove(d: Device) {
  const n = newRoom.value.trim(); if (!n) { adding.value = null; return }
  busy.value[d.id] = 'room'
  try { const r = await addRoom(n); store.rooms.push({ id: r.id, name: r.name, devices: [], intent: 'unknown' }); adding.value = null; await move(d, r.id) }
  catch (e: any) { notify(`Couldn't add the room: ${e.message}`, 'error'); delete busy.value[d.id] }
}

/* what the brain proposes for each new thing */
const suggestions = ref<Record<string, Suggestion>>({})
const thinking = ref(false), applying = ref(false)
const placeable = computed(() => props.room.devices.filter(d => suggestions.value[d.id]?.room).length)
async function think() {
  if (props.editing || !props.room.devices.length) return
  thinking.value = true
  try { const s = await getSuggestions(); const by: Record<string, Suggestion> = {}; for (const i of s.items) by[i.id] = i; suggestions.value = by } catch {}
  thinking.value = false
}
async function use(d: Device): Promise<boolean> {
  const s = suggestions.value[d.id]; if (!s || busy.value[d.id]) return false
  busy.value[d.id] = 'room'
  try {
    if (s.name && s.name !== d.name) { await renameDevice(d.id, s.name); d.name = s.name; names.value[d.id] = s.name }
    if (s.room) { await moveDevice(d.id, s.room); props.room.devices = props.room.devices.filter(x => x.id !== d.id); notify(`${s.name} is in the ${roomName(s.room)} now.`) }
    else notify(`Renamed to ${s.name}.`)
    delete suggestions.value[d.id]
  } catch (e: any) { notify(`Couldn't place it: ${e.message}`, 'error'); delete busy.value[d.id]; return false }
  delete busy.value[d.id]
  return true
}
async function useAll() {
  if (applying.value) return
  applying.value = true
  for (const d of [...props.room.devices]) if (suggestions.value[d.id]?.room && !(await use(d))) break   // the first refusal (a wrong code, the engine away) stops the run
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
        <p class="lede">{{ editing ? 'Rename anything, or move it to another room. Tap the tick when you are done.' : 'Check each name and say which room it lives in. It moves there on its own.' }}</p>
      </div>
    </header>

    <div class="suggest-bar" v-if="!editing && room.devices.length && (thinking || placeable)">
      <span class="suggest-lede"><Icon name="sparkle" :size="16" /><span>{{ thinking ? 'Working out where these go…' : placeable === 1 ? 'One of these looks like it has a home. Check it and tap Use.' : `${placeable} of these look like they have a home. Check them, or place them all.` }}</span></span>
      <button class="button small" v-if="placeable > 1" :class="{ busy: applying }" @click="useAll">Place all {{ placeable }}</button>
    </div>

    <ul class="sort" v-if="room.devices.length">
      <li v-for="d in room.devices" :key="d.id" class="sort-row" :class="{ busy: busy[d.id] }">
        <span class="sort-icon"><Icon :name="iconFor(d)" :size="20" /></span>
        <input class="sort-name" :value="names[d.id] ?? d.name" @input="names[d.id] = ($event.target as HTMLInputElement).value" @change="rename(d)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" aria-label="Name" />
        <template v-if="adding === d.id">
          <input class="sort-name" v-model="newRoom" placeholder="Name the room" autofocus @keydown.enter="createAndMove(d)" @keydown.escape="adding = null" />
          <button class="button small" @click="createAndMove(d)">Add</button>
        </template>
        <select v-else class="sort-room" :value="here" @change="move(d, ($event.target as HTMLSelectElement).value)" aria-label="Room">
          <option value="" disabled>Which room?</option>
          <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
          <option value="__new">A new room…</option>
        </select>
        <div class="suggest-line" v-if="!editing && suggestions[d.id]">
          <Icon name="sparkle" :size="14" />
          <span>Looks like <b>{{ suggestions[d.id].name }}</b><template v-if="suggestions[d.id].room"> in the <b>{{ roomName(suggestions[d.id].room) }}</b></template><span class="suggest-why" v-if="suggestions[d.id].why"> · {{ suggestions[d.id].why }}</span></span>
          <button class="button small" @click="use(d)">Use</button>
        </div>
      </li>
    </ul>
    <div v-else class="empty-room">
      <p class="empty">{{ editing ? 'Nothing left in this room.' : 'Everything has a room.' }}</p>
      <p class="empty-sub">{{ editing ? 'Everything moved elsewhere. Tap the tick to go back.' : 'Anything you add later that does not know where it lives will wait here.' }}</p>
    </div>
  </section>
</template>
