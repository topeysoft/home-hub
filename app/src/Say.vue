<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
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

/* At rest the box can be only its orb -- design/nightfall move 7, and it is the
   face that decides whether that happens, not this file. `open` is one fact in
   one place so the stylesheet never has to work out for itself whether there is
   anything in the box: it is open while somebody is in it, while it is carrying
   words, and while it is still finishing something. The last three matter more
   than they look. `busy` disables the input, which drops focus, so without it a
   box would shut on itself the moment a sentence was sent; and a note, an
   answer or a proposal is the box's reply, which nobody has read yet. */
const field = ref<HTMLInputElement | null>(null)
const focused = ref(false)
const open = computed(() => focused.value || !!text.value.trim() || busy.value || !!note.value || !!answer.value || !!proposal.value)
/* the whole pill is the way in, because at rest the orb is all there is to aim
   at and the input behind it is clipped to nothing */
function reach() { field.value?.focus() }

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
  /* and put the cursor back where it was. `busy` disables the input, which drops focus, and nothing
     was giving it back -- so after every sentence a keyboard was left outside the box and had to
     find its way in again. Under a face that rests the box, it also shut it on somebody who was
     plainly still talking to the house. */
  await nextTick(); field.value?.focus()
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
  <div class="say" :class="{ open }">
    <form class="search say-box" @submit.prevent="go" @click="reach">
      <!-- the orb: the house, listening. Drawn here rather than as a pseudo-element
           because under glass it is lit from inside by blooms turning against each
           other, and one ::before cannot hold two of them. Only the bottom bar shows
           it; everywhere else the box keeps its sparkle (panel.css). -->
      <span class="say-orb" aria-hidden="true"><i class="orb-cool"></i><i class="orb-warm"></i></span>
      <Icon name="sparkle" :size="18" />
      <input ref="field" v-model="text" :disabled="busy" @focus="focused = true" @blur="focused = false" :placeholder="room ? 'Tell this room…' : 'Tell the house…'" aria-label="Tell the house" enterkeyhint="send" autocomplete="off" autocapitalize="off" spellcheck="false" />
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
