<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { failed } from './code'
import { computed, nextTick, ref, watch } from 'vue'
import { store, notify, loadRoutines, loadRoofline, visibleRooms } from './store'
import { say, act, keepLook, dropLook, type Proposal, type Said } from './api'
import { canListen, listen, type Ear } from './ear'
import { speak, hush as quiet } from './mouth'
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
/* Move 6 of the eight, and the last one to find somewhere to live: the orb held
   at 1.18 for as long as somebody is talking, and one ring when the sentence
   lands. `listening` is the held state the canvas was not drawn with -- a tap
   has no letting go, so the house decides when you stopped, and the orb has to
   say it is still there. `landed` is the ring, which is one shot and not a
   state: it is taken off on its own animationend so a second sentence gets a
   second ring rather than nothing. design/nightfall Motion, 6 - Listening. */
const listening = ref(false)
const landed = ref(false)
let ear: Ear | null = null
/* Open while somebody is IN it -- typing, talking, or waiting on something in flight -- and no
   longer while its reply is merely unread. The replies hang above the bar on their own sheets and
   do not need the box wide to be read, and holding it open for them meant a sentence the house
   could not place left a 460px box on the wall with no way back to the orb but typing another one.
   A sentence somebody is still typing does keep it open, and `e2e/say.spec.ts` holds that. */
const open = computed(() => focused.value || listening.value || !!text.value.trim() || busy.value)
/* The whole pill is the way in, because at rest the orb is all there is to aim
   at and the input behind it is clipped to nothing.
   And the orb is the microphone -- settled 12 September 2026 -- but only where
   something can actually hear. Where nothing can, which is every house today,
   this is the line it has always been: the tap opens the box to type in. That
   is why the gesture was chosen over hold-to-talk. `ear.ts` has the rest. */
function reach() {
  if (listening.value) return hush()          // a second tap is how you stop
  if (open.value || !canListen()) return void field.value?.focus()
  /* a new sentence starts with the last one's answer cleared away -- the same thing `go` does for
     something typed, and without it the house appears to be answering what you are only now saying.
     `quiet()` is that same clearing for the half you hear: talking over the last answer is the one
     way a voice can be ruder than silence. */
  note.value = ''; answer.value = ''; proposal.value = null; quiet()
  ear = listen({
    /* the words as they arrive, so a long sentence visibly keeps the house's attention rather than
       looking like nothing is happening */
    hearing(sofar) { if (listening.value) text.value = sofar },
    heard(said) { text.value = said; ring(); hush(); go(true) },
    ended() { hush() },
    /* a microphone that will not start, or a browser that will not let it, says so where every
       other answer from the box already appears -- silence would read as the house ignoring you */
    failed(why) { hush(); note.value = why },
  })
  listening.value = !!ear
  if (!ear) field.value?.focus()
}
function hush() { ear?.stop(); ear = null; listening.value = false }
function ring() { landed.value = false; nextTick(() => { landed.value = true }) }

const hint = computed(() => {
  if (listening.value) return 'Listening…'
  const rooms = visibleRooms().filter(r => r.id !== 'unassigned' && r.devices.length)
  const here = props.room ? store.rooms.find(r => r.id === props.room) : null
  if (here) return `Try “lights off”, “movie” or “is anything on?”`
  const a = rooms.find(r => r.devices.some(d => d.capability === 'light'))?.name ?? 'kitchen'
  const b = rooms.find(r => r.devices.some(d => d.capability === 'media'))?.name ?? rooms[1]?.name ?? a
  return `Try “${a.toLowerCase()} lights off”, “movie in the ${b.toLowerCase()}” or “is anything on?”`
})

/* A LOOK FOR THE ROOFLINE, SAID (design/roofline/SaidC.dc.html, decided A with C). It is playing on the
   roof while this card is open, and kept only when told; "Not this", or walking away, puts the roof back.
   Each word is a chip, and tapping one says the sentence again with the next word in its place -- the
   same fixed grammar, so the vocabulary cannot grow from here. */
type Look = Extract<Said, { kind: 'look' }>
const look = ref<Look | null>(null)
const MOTION_WORDS = ['still', 'drifting', 'flickering', 'chasing', 'twinkling']
const COLOR_WORDS = ['red and green', 'red and white', 'orange and purple', 'red, white and blue']
const MOTION_OF: Record<string, string> = { still: 'still', drift: 'drifting', flicker: 'flickering', chase: 'chasing', twinkle: 'twinkling' }
const lookColors = computed(() => {
  const c = [...new Set(look.value?.colors ?? [])]
  return c.length < 2 ? c.join('') : `${c.slice(0, -1).join(', ')} and ${c[c.length - 1]}`
})
const lookColorsCap = computed(() => lookColors.value.charAt(0).toUpperCase() + lookColors.value.slice(1))
function sayLook(colors: string, motion: string, pace: string) {
  const l = look.value; if (!l) return
  text.value = `${l.occasion_name ? l.occasion_name + ': ' : ''}${colors}, ${motion}${pace ? ' ' + pace : ''}`
  go()
}
const nextMotion = () => { const l = look.value!; const m = MOTION_OF[l.motion] ?? l.motion; sayLook(lookColors.value, MOTION_WORDS[(MOTION_WORDS.indexOf(m) + 1) % 5], l.pace) }
const nextColors = () => { const l = look.value!; const i = COLOR_WORDS.indexOf(lookColors.value.replace(/,? and /g, ' and ').replace(/, /g, ', ')); sayLook(COLOR_WORDS[(i + 1) % COLOR_WORDS.length], MOTION_OF[l.motion] ?? l.motion, l.pace) }
const nextPace = () => { const l = look.value!; sayLook(lookColors.value, MOTION_OF[l.motion] ?? l.motion, l.pace === 'quickly' ? 'slowly' : 'quickly') }
const keeping = ref(false)
async function keepIt() {
  if (keeping.value) return
  keeping.value = true
  try { await keepLook(); notify(`Kept for ${look.value?.occasion_name ?? 'the roofline'}.`); look.value = null; loadRoofline() }
  catch (e: any) { notify(e.message, 'error') }
  keeping.value = false
}
async function notThis() { look.value = null; try { await dropLook(); loadRoofline() } catch {} }

/* Opened from somewhere else with the start of a sentence already in it -- the Roofline's "Say another
   look" -- so what is typed next finishes it. The last answer goes, as it does for any new sentence. */
watch(() => store.sayStart, async (start) => {
  if (start == null) return
  store.sayStart = null
  hush(); note.value = ''; answer.value = ''; proposal.value = null; look.value = null
  text.value = start
  await nextTick()
  field.value?.focus()
}, { immediate: true })

async function go(spoken = false) {
  const said = text.value.trim()
  if (!said || busy.value) return
  busy.value = true; note.value = ''; answer.value = ''; proposal.value = null; look.value = null
  try {
    const r = await say(said, props.room, spoken)
    text.value = ''
    /* Out loud only where the sentence ARRIVED out loud -- docs/voice.md: the route decides, not the
       kind. Nobody types at a wall and wants it to talk back. The brain keeps this same rule and only
       mints a clip for a spoken turn, so this is the panel agreeing rather than the panel deciding. */
    if (spoken) speak(r)
    if (r.kind === 'done') notify(r.text)
    else if (r.kind === 'answer') answer.value = r.text
    else if (r.kind === 'explain') answer.value = r.answer
    else if (r.kind === 'action') { proposal.value = r; note.value = 'Ready when you are. Nothing happens until you tap.' }
    else if (r.kind === 'rule') { note.value = 'Written up as a routine. It waits for your OK under Routines.'; loadRoutines() }
    else if (r.kind === 'look') look.value = r
  } catch (e: any) {
    /* What was said goes into the answer rather than being left in the box. A spoken sentence is not
       "a sentence somebody is still typing" -- nobody is mid-word -- so leaving it there only held
       the box open, and the house repeating what it heard is the more useful half of it anyway. */
    note.value = spoken && said ? `“${said}” — ${e.message}` : e.message
    /* and said, always. docs/voice.md is firm about this one: silence when the house did not catch
       you reads as being ignored, which is the lesson the note above already learned on the screen. */
    if (spoken) speak(e)
  }
  if (spoken) text.value = ''
  busy.value = false
  /* and put the cursor back where it was. `busy` disables the input, which drops focus, and nothing
     was giving it back -- so after every sentence a keyboard was left outside the box and had to
     find its way in again. Under a face that rests the box, it also shut it on somebody who was
     plainly still talking to the house. */
  if (!spoken) { await nextTick(); field.value?.focus() }
}
async function doIt() {
  const p = proposal.value; if (!p || doing.value) return
  doing.value = true
  try { await act(p.device, p.action, Object.keys(p.data).length ? p.data : undefined); notify(p.name); proposal.value = null; note.value = '' }
  catch (e: any) { notify(failed('That didn’t work', e), 'error') }
  doing.value = false
}
</script>

<template>
  <div class="say" :class="{ open, listening }">
    <form class="search say-box" @submit.prevent="go()" @click="reach">
      <!-- the orb: the house, listening. Drawn here rather than as a pseudo-element
           because under glass it is lit from inside by blooms turning against each
           other, and one ::before cannot hold two of them. Only the bottom bar shows
           it; everywhere else the box keeps its sparkle (panel.css). -->
      <span class="say-orb" aria-hidden="true"><i class="orb-cool"></i><i class="orb-warm"></i></span>
      <Icon name="sparkle" :size="18" />
      <input ref="field" v-model="text" :disabled="busy" @focus="focused = true" @blur="focused = false" :placeholder="room ? 'Tell this room…' : 'Tell the house…'" aria-label="Tell the house" enterkeyhint="send" data-keys="command" :data-room="room ?? undefined" autocomplete="off" autocapitalize="off" spellcheck="false" />
      <button class="button small" type="submit" :class="{ busy }" :disabled="!text.trim()">{{ busy ? 'Doing…' : 'Go' }}</button>
    </form>
    <!-- the ring, once per sentence. A sibling of the box and not a child of it:
         the pill is `overflow: hidden` under glass and would clip it at 56px,
         and the orb is clipped tighter still to keep its blooms round. -->
    <i class="say-ring" v-if="landed" aria-hidden="true" @animationend="landed = false"></i>
    <div class="say-look" v-if="look">
      <span class="say-look-for">For {{ look.occasion_name ?? 'tonight' }}, on the roofline</span>
      <div class="say-look-words">
        <button class="say-look-word" @click="nextColors">{{ lookColorsCap }}</button><span class="say-look-comma">,</span>
        <button class="say-look-word on" @click="nextMotion">{{ MOTION_OF[look.motion] ?? look.motion }}</button>
        <button class="say-look-word" v-if="look.pace" @click="nextPace">{{ look.pace }}</button>
      </div>
      <p class="say-look-note">Tap a word to change it. <span class="say-look-live">●</span> Playing on the roof now — it goes back to how it was if you walk away.</p>
      <div class="draft-actions">
        <button class="button small" :class="{ busy: keeping }" :disabled="!look.occasion" @click="keepIt">Keep it for {{ look.occasion_name ?? 'an occasion' }}</button>
        <button class="button small ghost" @click="notThis">Not this</button>
      </div>
    </div>
    <p class="say-hint" v-if="!note && !answer && !proposal && !look" :aria-live="listening ? 'polite' : undefined">{{ hint }}</p>
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
