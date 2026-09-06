<script setup lang="ts">
import { computed, ref } from 'vue'
import { addRoom, moveDevice, renameDevice, type Device, type Room } from './api'
import { store, cap, notify } from './store'
import Icon from './Icon.vue'

/* The "New devices" room: everything that has not been put in a room yet, each with a name to
   check and a room to pick. Once placed, a device leaves this list on its own. */
const props = defineProps<{ room: Room }>()
defineEmits<{ back: [] }>()
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const names = ref<Record<string, string>>({})
const busy = ref<Record<string, string>>({})
const adding = ref<string | null>(null), newRoom = ref('')
const iconFor = (d: Device) => cap(d) === 'media' && /\b(tv|television|roku)\b/i.test(d.name) ? 'tv' : cap(d)

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
    const r = rooms.value.find(r => r.id === roomId)
    notify(`${d.name} is in the ${r?.name ?? 'room'} now.`)
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
</script>

<template>
  <section class="room">
    <header class="stage-head room-head">
      <button class="back" @click="$emit('back')" aria-label="Back to home"><Icon name="back" :size="22" /></button>
      <div>
        <h1 class="display">New devices</h1>
        <p class="lede">Check each name and say which room it lives in. It moves there on its own.</p>
      </div>
    </header>

    <ul class="sort" v-if="room.devices.length">
      <li v-for="d in room.devices" :key="d.id" class="sort-row" :class="{ busy: busy[d.id] }">
        <span class="sort-icon"><Icon :name="iconFor(d)" :size="20" /></span>
        <input class="sort-name" :value="names[d.id] ?? d.name" @input="names[d.id] = ($event.target as HTMLInputElement).value" @change="rename(d)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" aria-label="Name" />
        <template v-if="adding === d.id">
          <input class="sort-name" v-model="newRoom" placeholder="Name the room" autofocus @keydown.enter="createAndMove(d)" @keydown.escape="adding = null" />
          <button class="button small" @click="createAndMove(d)">Add</button>
        </template>
        <select v-else class="sort-room" :value="''" @change="move(d, ($event.target as HTMLSelectElement).value)" aria-label="Room">
          <option value="" disabled>Which room?</option>
          <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
          <option value="__new">A new room…</option>
        </select>
      </li>
    </ul>
    <div v-else class="empty-room">
      <p class="empty">Everything has a room.</p>
      <p class="empty-sub">Anything you add later that does not know where it lives will wait here.</p>
    </div>
  </section>
</template>
