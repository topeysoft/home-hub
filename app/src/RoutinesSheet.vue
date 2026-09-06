<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify, loadRoutines, loadAssistant, visibleRooms } from './store'
import { enableRoutine, draftRoutine, approveDraft, discardDraft, setAssistantKey, type Routine } from './api'
import { routineWords } from './why'
import Icon from './Icon.vue'

/* The routines sheet: every rule by room with a switch; the assistant's drafts waiting for an OK; and a box to ask for one
   in plain words. The panel never edits a rule by hand. */
const busy = ref('')
const groups = computed(() => {
  const order = ['home', ...visibleRooms().map(r => r.id)]
  const by = new Map<string, Routine[]>()
  for (const r of store.routines) by.set(r.room, [...(by.get(r.room) ?? []), r])
  const rank = (id: string) => { const i = order.indexOf(id); return i < 0 ? 999 : i }
  return [...by.keys()].sort((a, b) => rank(a) - rank(b))
    .map(id => ({ id, name: roomName(id), rules: by.get(id)! }))
})
const roomName = (id: string) => id === 'home' ? 'Whole house' : store.rooms.find(r => r.id === id)?.name ?? id
const on = (r: Routine) => r.enabled !== false

async function flip(r: Routine) {
  if (busy.value) return
  const want = !on(r)
  busy.value = r.id; r.enabled = want
  try { await enableRoutine(r.id, want) } catch (e: any) { r.enabled = !want; notify(`That didn't stick: ${e.message}`, 'error') }
  busy.value = ''
}

/* asking for one */
const text = ref(''), asking = ref(false), note = ref('')
async function ask() {
  const said = text.value.trim()
  if (!said || asking.value) return
  asking.value = true; note.value = ''
  try {
    const d = await draftRoutine(said)
    text.value = ''
    if (!store.drafts.some(x => x.id === d.id)) store.drafts = [...store.drafts, d]   // the stream usually beats us to it
    note.value = 'Here it is. Read it over, then approve it or let it go.'
  } catch (e: any) { note.value = e.message }
  asking.value = false
}
async function approve(d: Routine) {
  if (busy.value) return
  busy.value = d.id
  try { await approveDraft(d.id); store.drafts = store.drafts.filter(x => x.id !== d.id); notify(`${d.name} is on.`); loadRoutines() }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}
async function discard(d: Routine) {
  if (busy.value) return
  busy.value = d.id
  try { await discardDraft(d.id); store.drafts = store.drafts.filter(x => x.id !== d.id) } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}

/* connecting the assistant, when nobody put a key on the hub */
const key = ref(''), connecting = ref(false), keyNote = ref('')
async function connect() {
  if (!key.value.trim() || connecting.value) return
  connecting.value = true; keyNote.value = ''
  try { store.assistant = await setAssistantKey(key.value.trim()); key.value = ''; notify('The assistant is connected.') }
  catch (e: any) { keyNote.value = e.message }
  connecting.value = false
}

function close() { store.sheet = null }
function keydown(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => { window.addEventListener('keydown', keydown); loadRoutines(); loadAssistant() })
onUnmounted(() => window.removeEventListener('keydown', keydown))
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="Routines">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">Routines</h2>
      <p class="sheet-lede">Small things the house does on its own. Switch one off and it stops until you switch it back. A scene you pick by hand always wins for a while.</p>

      <div class="ask" v-if="store.assistant?.configured">
        <form class="search" @submit.prevent="ask">
          <Icon name="sparkle" :size="18" />
          <input v-model="text" :disabled="asking" placeholder="Say what you'd like the house to do…" aria-label="Ask for a routine" />
          <button class="button small" type="submit" :class="{ busy: asking }" :disabled="!text.trim()">{{ asking ? 'Thinking…' : 'Ask' }}</button>
        </form>
        <p class="sheet-status" v-if="note">{{ note }}</p>
      </div>
      <details class="section" v-else-if="store.assistant?.available">
        <summary>Connect the assistant to ask for routines in plain words</summary>
        <p class="field-hint">Paste a key from the model's maker. It stays on the hub; the assistant only ever sees this list and the house's log.</p>
        <form class="search" @submit.prevent="connect">
          <input v-model="key" type="password" :disabled="connecting" placeholder="Paste the key" aria-label="Assistant key" />
          <button class="button small" type="submit" :class="{ busy: connecting }" :disabled="!key.trim()">{{ connecting ? 'Checking…' : 'Connect' }}</button>
        </form>
        <p class="field-err" v-if="keyNote">{{ keyNote }}</p>
      </details>

      <template v-if="store.drafts.length">
        <h3 class="label routines-head">Waiting for your OK</h3>
        <ul class="drafts">
          <li v-for="d in store.drafts" :key="d.id">
            <span class="routine-text">
              <span class="routine-name">{{ d.name }}</span>
              <span class="routine-sub">{{ roomName(d.room) }} · {{ routineWords(d) }}</span>
              <span class="draft-said" v-if="d.said">You said: “{{ d.said }}”</span>
            </span>
            <span class="draft-actions">
              <button class="button small" :class="{ busy: busy === d.id }" @click="approve(d)">Approve</button>
              <button class="button small ghost" :class="{ busy: busy === d.id }" @click="discard(d)">Discard</button>
            </span>
          </li>
        </ul>
      </template>

      <template v-for="g in groups" :key="g.id">
        <h3 class="label routines-head">{{ g.name }}</h3>
        <ul class="routines">
          <li v-for="r in g.rules" :key="r.id" :class="{ off: !on(r) }">
            <span class="routine-text"><span class="routine-name">{{ r.name }}</span><span class="routine-sub">{{ routineWords(r) }}</span></span>
            <button class="toggle" role="switch" :aria-checked="on(r)" :aria-label="`${r.name}: ${on(r) ? 'on' : 'off'}`" :class="{ on: on(r), busy: busy === r.id }" @click="flip(r)"><span class="knob"></span></button>
          </li>
        </ul>
      </template>
      <p class="sheet-status" v-if="!store.routines.length && !store.routineErrors.length && !store.drafts.length">No routines yet. The house only does what you tell it.</p>
      <div class="add-block" v-if="store.routineErrors.length">
        <h3 class="label routines-head">Couldn't be read</h3>
        <p class="sheet-status">Some routines on the hub have a mistake in them and are skipped until it is fixed:</p>
        <ul class="routine-errors"><li v-for="e in store.routineErrors" :key="e">{{ e }}</li></ul>
      </div>
      <p class="sheet-foot" v-if="store.assistant?.configured">A routine you ask for waits above until you approve it. Nothing runs without your OK.</p>
      <p class="sheet-foot" v-else>For now, new routines are added on the hub itself. Connect the assistant to ask for one in plain words.</p>
    </div>
  </div>
</template>
