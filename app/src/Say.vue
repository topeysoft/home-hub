<script setup lang="ts">
import { computed, ref } from 'vue'
import { store, notify, loadRoutines, visibleRooms } from './store'
import { say, act, type Proposal } from './api'
import Icon from './Icon.vue'

/* The command box. A sentence goes to the brain, whose fixed grammar runs it at once the way a tap does ("kitchen
   lights off", "movie in the den", "is the front door locked?"). What the grammar cannot place goes to the assistant,
   which only proposes: an action to confirm here, or a routine to approve under Routines. Every sentence is kept,
   understood or not, so the grammar can grow from what people actually say. `room` is the room the panel is showing,
   so "lights off" inside a room means that room. */
const props = defineProps<{ room?: string | null }>()
const text = ref(''), busy = ref(false), note = ref(''), answer = ref(''), proposal = ref<(Proposal & { said: string }) | null>(null), doing = ref(false)

const hint = computed(() => {
  const rooms = visibleRooms().filter(r => r.id !== 'unassigned' && r.devices.length)
  const here = props.room ? store.rooms.find(r => r.id === props.room) : null
  if (here) return `Try “lights off”, “movie” or “is anything on?”`
  const a = rooms.find(r => r.devices.some(d => d.capability === 'light'))?.name ?? 'kitchen'
  const b = rooms.find(r => r.devices.some(d => d.capability === 'media'))?.name ?? rooms[1]?.name ?? a
  return `Try “${a.toLowerCase()} lights off”, “movie in the ${b.toLowerCase()}” or “is anything on?”`
})

async function go() {
  const said = text.value.trim()
  if (!said || busy.value) return
  busy.value = true; note.value = ''; answer.value = ''; proposal.value = null
  try {
    const r = await say(said, props.room)
    text.value = ''
    if (r.kind === 'done') notify(r.text)
    else if (r.kind === 'answer') answer.value = r.text
    else if (r.kind === 'explain') answer.value = r.answer
    else if (r.kind === 'action') { proposal.value = r; note.value = 'Ready when you are. Nothing happens until you tap.' }
    else if (r.kind === 'rule') { note.value = 'Written up as a routine. It waits for your OK under Routines.'; loadRoutines() }
  } catch (e: any) { note.value = e.message }
  busy.value = false
}
async function doIt() {
  const p = proposal.value; if (!p || doing.value) return
  doing.value = true
  try { await act(p.device, p.action, Object.keys(p.data).length ? p.data : undefined); notify(p.name); proposal.value = null; note.value = '' }
  catch (e: any) { notify(`That didn't work: ${e.message}`, 'error') }
  doing.value = false
}
</script>

<template>
  <div class="say">
    <form class="search say-box" @submit.prevent="go">
      <Icon name="sparkle" :size="18" />
      <input v-model="text" :disabled="busy" :placeholder="room ? 'Tell this room…' : 'Tell the house…'" aria-label="Tell the house" enterkeyhint="send" autocomplete="off" autocapitalize="off" spellcheck="false" />
      <button class="button small" type="submit" :class="{ busy }" :disabled="!text.trim()">{{ busy ? 'Doing…' : 'Go' }}</button>
    </form>
    <p class="say-hint" v-if="!note && !answer && !proposal">{{ hint }}</p>
    <p class="say-answer" v-if="answer"><Icon name="sparkle" :size="14" /><span>{{ answer }}</span></p>
    <p class="say-note" v-if="note">{{ note }} <button class="linkish" v-if="note.includes('Routines')" @click="store.sheet = 'routines'">Open Routines</button></p>
    <ul class="drafts" v-if="proposal">
      <li>
        <span class="routine-text">
          <span class="routine-name">{{ proposal.name }}</span>
          <span class="routine-sub">{{ proposal.device_name }} · right now, once</span>
          <span class="draft-said">You said: “{{ proposal.said }}”</span>
        </span>
        <span class="draft-actions">
          <button class="button small" :class="{ busy: doing }" @click="doIt">Do it</button>
          <button class="button small ghost" @click="proposal = null; note = ''">Not now</button>
        </span>
      </li>
    </ul>
  </div>
</template>
