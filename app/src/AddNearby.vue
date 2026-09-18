<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { nearbySwitches, blinkSwitch, letSwitchIn, moveDevice, type Waiting, type Letting } from './api'
import { store, notify } from './store'
import Icon from './Icon.vue'

/*
 * Letting in a switch whose code you cannot reach.
 *
 * The code on a switch's back is not a password -- the mesh never demanded it, and every switch on
 * this house's network was claimed without one. What it buys is knowing WHICH switch, and a switch
 * screwed to a wall has its code facing the plasterboard, so that has to be proved another way.
 *
 * It is proved by the switch itself. The house asks what is waiting, makes one announce itself, and
 * a person says whether the blinking one is the switch they just touched. Same idea as the puck's
 * own arrival: THE IDENTITY CHECK IS THE OBJECT, NOT A NUMBER.
 *
 * WHICH MEANS NO CAMERA, so the wall can run this alone -- "the wall shows, the phone scans" exists
 * only because a code must be read, and here there is none. This screen is the same on both.
 *
 * It blinks them ONE AT A TIME. A room with two blinking switches in it answers nothing.
 *
 * design/puck/Held.dc.html and design/puck/Waiting.dc.html.
 */
const emit = defineEmits<{ close: [], code: [] }>()

type Step = 'looking' | 'none' | 'asking' | 'letting' | 'done' | 'failed'
const step = ref<Step>('looking')
const waiting = ref<Waiting[]>([])
const spokenFor = ref<Waiting[]>([])
const at = ref(0)                       // which candidate is being offered
const said = ref('')
const got = ref<Letting | null>(null)
const busy = ref(false)

const here = computed(() => waiting.value[at.value])
const more = computed(() => waiting.value.length - at.value - 1)

async function look() {
  step.value = 'looking'
  said.value = ''
  try {
    const r = await nearbySwitches()
    if (r.state === 'failed') { step.value = 'failed'; said.value = r.text ?? ''; return }
    waiting.value = r.waiting ?? []
    spokenFor.value = r.claimed_elsewhere ?? []
    at.value = 0
    if (!waiting.value.length) { step.value = 'none'; said.value = r.text ?? ''; return }
    await offer()
  } catch (e: any) { step.value = 'failed'; said.value = e.message }
}

/* Blink the one being offered. If it cannot be reached there is nothing honest left to ask about it,
   so that is a failure of this candidate rather than of the whole job: move on. */
async function offer() {
  const who = here.value
  if (!who?.uuid) { step.value = 'none'; return }
  step.value = 'asking'
  busy.value = true
  try { await blinkSwitch(who.uuid, 5) } catch { /* it may still be the right one; let them look */ }
  busy.value = false
}

function notThisOne() {
  if (more.value > 0) { at.value++; offer() }
  else { step.value = 'none'; said.value = 'That was the last one it could hear.' }
}

async function yesThatOne() {
  const who = here.value
  if (!who?.uuid) return
  step.value = 'letting'
  try {
    const r = await letSwitchIn(who.uuid)
    got.value = r
    step.value = r.state === 'failed' ? 'failed' : 'done'
    said.value = r.text ?? ''
  } catch (e: any) { step.value = 'failed'; said.value = e.message }
}

/* The one question at the end, the same as every other way in. */
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const placing = ref('')
async function place(id: string) {
  if (!got.value?.device_id) return
  placing.value = id
  try {
    await moveDevice(got.value.device_id, id)
    notify(`${got.value.name || 'It'} is in the ${rooms.value.find(r => r.id === id)?.name} now.`)
    emit('close')
  } catch (e: any) { notify(e.message, 'error'); placing.value = '' }
}

onMounted(look)
</script>

<template>
  <div class="flow add-switch">
    <h3 class="flow-title">Add a wall switch</h3>

    <template v-if="step === 'looking'">
      <p class="flow-desc pulse">Listening for a switch that is asking to be let in&hellip;</p>
      <div class="bridge-bar"><i style="width: 40%"></i></div>
      <p class="sheet-status">A few seconds.</p>
    </template>

    <!-- Nothing claimable. Which is two different situations wanting opposite things said. -->
    <template v-else-if="step === 'none'">
      <p class="flow-desc">{{ said || 'Nothing nearby is asking to be let in.' }}</p>
      <div class="bridge-row" v-if="spokenFor.length" style="margin-bottom: 18px">
        <span class="bridge-icon"><Icon name="switch" :size="18" /></span>
        <span class="bridge-text">
          <span class="bridge-name">{{ spokenFor.length === 1 ? 'One is on another network' : `${spokenFor.length} are on another network` }}</span>
          <span class="bridge-sub">Pull its little tab out and push it back, then hold a finger flat on it until it blinks. Then look again.</span>
        </span>
      </div>
      <p class="flow-desc" v-else>A switch out of a box is already asking, with nothing to press. One that has been set up before needs its tab pulled out and pushed back, then a finger held on it until it blinks.</p>
      <div class="flow-actions">
        <button class="button" @click="look">Look again</button>
        <button class="button ghost" @click="emit('code')">I can reach the code</button>
      </div>
    </template>

    <!-- The identity check: one blinking switch, one question. -->
    <template v-else-if="step === 'asking'">
      <p class="flow-desc">
        {{ waiting.length === 1 ? 'One switch is waiting.' : `${waiting.length} switches are waiting.` }}
        It should be blinking now.
      </p>
      <div class="press-line" style="margin-bottom: 18px">
        <span class="press-said"><span class="pulse-dot"></span>Is the blinking one the switch you just touched?</span>
      </div>
      <div class="flow-actions">
        <button class="button" :class="{ busy }" @click="yesThatOne">Yes, that is it</button>
        <button class="button ghost" @click="notThisOne">
          {{ more > 0 ? 'No — try the next one' : 'No, none of them' }}
        </button>
      </div>
      <p class="sheet-status" v-if="more > 0">{{ more }} more it can hear.</p>
      <p class="sheet-status" v-else-if="waiting.length > 1">The last one it can hear.</p>
    </template>

    <template v-else-if="step === 'letting'">
      <p class="flow-desc pulse">Letting it into the house &mdash; it learns the house&rsquo;s keys, then says hello to the bridge.</p>
      <div class="bridge-bar"><i style="width: 52%"></i></div>
      <p class="sheet-status">Around half a minute. You can put your phone down.</p>
    </template>

    <template v-else-if="step === 'done'">
      <p class="flow-done"><span class="done-icon"><Icon name="check" :size="20" /></span>It&rsquo;s in. {{ said || 'A light that dims, and a motion sensor.' }}</p>
      <template v-if="got?.device_id">
        <p class="flow-desc">Which room is it in?</p>
        <div class="press-rooms">
          <button v-for="r in rooms" :key="r.id" class="chip-btn" :class="{ on: placing === r.id }" @click="place(r.id)">{{ r.name }}</button>
        </div>
        <div class="flow-actions"><button class="button ghost" @click="emit('close')">Later</button></div>
      </template>
      <div class="flow-actions" v-else><button class="button" @click="emit('close')">Done</button></div>
    </template>

    <template v-else>
      <p class="flow-desc">{{ said || 'That switch would not join.' }}</p>
      <div class="flow-actions">
        <button class="button" @click="look">Try again</button>
        <button class="button ghost" @click="emit('close')">Not now</button>
      </div>
    </template>
  </div>
</template>
