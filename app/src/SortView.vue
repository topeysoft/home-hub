<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { addRoom, moveDevice, renameDevice, forgetDevice, getSuggestions, type Device, type Room, type Suggestion } from './api'
import { store, cap, notify } from './store'
import Icon from './Icon.vue'
import { pressedIn, snapshot, type Seen } from './pressed'

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
    // eslint-disable-next-line vue/no-mutating-props -- the row leaves now and the house confirms with a rebuild; waiting for the round trip would leave it sitting there
    props.room.devices = props.room.devices.filter(x => x.id !== d.id)
  } catch (e: any) { notify(`Couldn't move it: ${e.message}`, 'error') }
  delete busy.value[d.id]
}
/* The end of a thing's life here. One tap asks with the name in it, so what disappears is said before it
   does; the second does it. Not offered on New devices, where a thing that is forgotten is only rediscovered. */
const forgetting = ref('')
async function forget(d: Device) {
  if (forgetting.value !== d.id) { forgetting.value = d.id; return }
  busy.value[d.id] = 'forget'
  try {
    await forgetDevice(d.id)
    notify(`${d.name} is forgotten.`)
    // eslint-disable-next-line vue/no-mutating-props -- as with a move: the row goes now and the rebuild confirms it
    props.room.devices = props.room.devices.filter(x => x.id !== d.id)
  } catch (e: any) { notify(e.message, 'error') }
  forgetting.value = ''
  delete busy.value[d.id]
}
async function createAndMove(d: Device) {
  const n = newRoom.value.trim(); if (!n) { adding.value = null; return }
  busy.value[d.id] = 'room'
  try { const r = await addRoom(n); store.rooms.push({ id: r.id, name: r.name, devices: [], intent: 'unknown' }); adding.value = null; await move(d, r.id) }
  catch (e: any) { notify(`Couldn't add the room: ${e.message}`, 'error'); delete busy.value[d.id] }
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
   a rename or a move makes no state event, so a press is the only thing left. */
const PRESS_FOR = 45000
const pressed = ref<{ id: string; at: number } | null>(null)
const now = ref(Date.now())
const live = computed(() => pressed.value && now.value - pressed.value.at < PRESS_FOR ? pressed.value.id : null)
/* Only things that can announce themselves: a wall switch does, a bulb behind a bridge does, a camera
   does not. Saying "go and press one" over a list of things that cannot answer would be a lie. */
const CAN_PRESS = ['light', 'switch', 'cover', 'lock']
const pressable = computed(() => props.room.devices.filter(d => CAN_PRESS.includes(cap(d))))
const teach = computed(() => !props.editing && pressable.value.length > 1)
/* The press itself, in pressed.ts -- and it is the only thing this screen watches. */
let seen: Seen = {}
watch(() => props.room.devices.map(d => `${d.id}:${d.state}`).join(), () => {
  const was = seen
  seen = snapshot(props.room.devices)
  const hit = pressedIn(was, pressable.value, id => !!busy.value[id])
  if (!hit) return
  pressed.value = { id: hit, at: Date.now() }
  now.value = Date.now()
  setTimeout(() => document.querySelector('.sort-row.pressed')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 30)
}, { immediate: true })
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(tick))
/* what a pressed thing turned out to be, in its own words rather than its address */
function what(d: Device) {
  const c = cap(d), bits: string[] = []
  if (c === 'light') bits.push(d.attrs?.brightness != null ? 'A light that dims' : 'A light')
  else if (c === 'switch') bits.push('A switch')
  else if (c === 'lock') bits.push('A lock')
  else if (c === 'cover') bits.push('A blind')
  if (d.attrs?.has_motion || /motion/i.test(d.name)) bits.push('with a motion sensor in it')
  return bits.join(', ') + '.'
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
    // eslint-disable-next-line vue/no-mutating-props -- as above: the placed device leaves the list at once
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
        <p class="lede">{{ editing ? 'Rename anything, move it to another room, or forget it for good. Tap the tick when you are done.' : 'Check each name and say which room it lives in. It moves there on its own.' }}</p>
      </div>
    </header>

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
      <li v-for="d in room.devices" :key="d.id" class="sort-row" :class="{ busy: busy[d.id], pressed: live === d.id }">
        <span class="sort-icon"><Icon :name="iconFor(d)" :size="20" /></span>
        <!-- on the pressed card the name is asked below, in words, so the header shows it and does not ask twice -->
        <span class="sort-name still" v-if="live === d.id && !editing">{{ names[d.id] ?? d.name }}</span>
        <input v-else class="sort-name" :value="names[d.id] ?? d.name" @input="names[d.id] = ($event.target as HTMLInputElement).value" @change="rename(d)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" aria-label="Name" />
        <template v-if="adding === d.id">
          <input class="sort-name" v-model="newRoom" placeholder="Name the room" autofocus @keydown.enter="createAndMove(d)" @keydown.escape="adding = null" />
          <button class="button small" @click="createAndMove(d)">Add</button>
        </template>
        <select v-else-if="live !== d.id || editing" class="sort-room" :value="here" @change="move(d, ($event.target as HTMLSelectElement).value)" aria-label="Room">
          <option value="" disabled>Which room?</option>
          <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
          <option value="__new">A new room…</option>
        </select>
        <button v-if="editing && adding !== d.id" class="button small ghost sort-forget" :class="{ warn: forgetting === d.id }" @click="forget(d)">{{ forgetting === d.id ? 'Forget?' : 'Forget' }}</button>
        <p class="sort-forget-ask" v-if="forgetting === d.id"><b>{{ d.name }}</b> goes from the house, and from whatever brought it. Tap again to do it.</p>
        <!-- the one that was just pressed: the rooms as chips, because the answer is one tap away
             and a dropdown would hide it behind two -->
        <div class="press-line" v-if="live === d.id && !editing">
          <!-- "you pressed" and not "it came on": the house knows the switch reported a change because a hand
               was on it, and nothing more. A stairway's companion switch has no load wired to it at all, and
               there is no way yet to tell one from the mesh -- so the row says what is true of both. -->
          <span class="press-said"><span class="pulse-dot"></span>You just pressed this one. {{ what(d) }}</span>
          <!-- the name, asked in words at the one moment the person knows what the thing is. The same
               field as the row's own (it saves when you leave it); the brain's suggestion fills it in. -->
          <label class="press-name">
            <span class="field-label">Call it</span>
            <input class="input" :value="names[d.id] ?? suggestions[d.id]?.name ?? d.name" @input="names[d.id] = ($event.target as HTMLInputElement).value" @change="rename(d)" @keydown.enter="($event.target as HTMLInputElement).blur()" spellcheck="false" autocapitalize="words" aria-label="Name" />
          </label>
          <span class="field-label">Which room is it in?</span>
          <div class="press-rooms">
            <button v-for="r in rooms" :key="r.id" class="chip-btn" @click="move(d, r.id)">{{ r.name }}</button>
            <button class="chip-btn ghost" @click="move(d, '__new')">Another room…</button>
          </div>
        </div>
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
