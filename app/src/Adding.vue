<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { moveDevice, renameDevice } from './api'
import { store, notify, refreshFound, loadHealth } from './store'
import { doors, type Act, type Caught, type Door, type Proof, type Working } from './adding'
import Icon from './Icon.vue'
import Blink from './prove/Blink.vue'
import Press from './prove/Press.vue'
import Code from './prove/Code.vue'
import SignIn from './prove/SignIn.vue'
import House from './prove/House.vue'

/*
 * THE SHELL. It owns the four beats and every button on them, and it knows nothing about radios.
 *
 * 1 choose   what have you got -- four doors, and whatever is already waiting
 * 2 prove    which one is yours -- one of the pieces in prove/, which draws its middle and nothing else
 * 3 working  letting it in -- one bar, one sentence, one honest how-long
 * 4 in       it's in, which room -- the same ending for every route
 *
 * A piece never draws a title, a button or a progress bar of its own: it says what it needs from the
 * person, and hands back `working`, `caught` or `wrong`. Which is why every route ends up saying the
 * same words -- there is only one place left that says them. design/adding/Shell.dc.html.
 *
 * The piece STAYS MOUNTED through beat three, hidden, because it is the thing doing the work and
 * unmounting it would cancel what it is waiting on.
 */
const emit = defineEmits<{ busy: [boolean] }>()
/* A conversation the house already has open, handed over by whatever offered it (signing an account
   in again from Home). It is the same machinery as adding by brand, so it opens that piece directly. */
const props = defineProps<{ resume?: string | null }>()

const PIECE = { blink: Blink, press: Press, code: Code, signin: SignIn, house: House }
type Beat = 'choose' | 'prove' | 'working' | 'in' | 'wrong'

const beat = ref<Beat>('choose')
/* What the conversation is about, in the door's own words. It is a string and not the door itself
   because nothing past beat one needs the rest of a door -- and because the things that turn up on
   their own have a name but never had a door. */
const where = ref('')
/* The proof is the door's to begin with, and the piece's to change: a switch whose code can be
   reached swaps blink for code without leaving the conversation, and the heading stays put. */
const proof = ref<Proof | null>(null)
const hint = ref<string | null>(null)      // a flow id or a code mode the piece is opened on
const work = ref<Working | null>(null)
const got = ref<Caught | null>(null)
const wrong = ref<{ text: string; retry: boolean } | null>(null)
const attempt = ref(0)                     // bumping this remounts the piece, which is what Try again means
/* What the piece wants offering besides leaving. It says what it needs; this screen says it in the
   house's words, in the house's order, with "Not now" after it. */
const acts = ref<Act[]>([])
/* A piece may rename the screen it is on -- a maker's form has its own title, and a flow that gave up
   says so in the heading. It never gets to draw that heading itself. */
const said = ref('')

const open = computed(() => beat.value !== 'choose')
watch(open, v => emit('busy', v), { immediate: true })

/* The heading is the door's, for the whole conversation. What you touched stays put: choosing a door
   does not make it vanish, it becomes the name of the screen it opened. */
const heading = computed(() => {
  if (beat.value === 'prove' && said.value) return said.value
  if (beat.value === 'in') return 'It’s in.'
  if (beat.value === 'wrong') return 'It would not join.'
  if (beat.value === 'working') return work.value?.text ?? 'Letting it in…'
  return where.value || 'What are you adding?'
})

/* Everything a conversation carried, put down. Called on the way into one and on the way out of it,
   so no answer from the last one can be left lying on the screen of the next. */
function clear() {
  wrong.value = null; got.value = null; work.value = null; acts.value = []; said.value = ''
}
function knock(d: Door) {
  clear(); where.value = d.title; proof.value = d.proof; hint.value = null
  beat.value = 'prove'
}
/* Something already waiting is beat one already answered: it opens the piece that can finish it. */
function open_(p: Proof, on: string | null, title: string) {
  clear(); where.value = title; proof.value = p; hint.value = on
  beat.value = 'prove'
}

/* ---- what the pieces hand back ---- */
/* Beat three has nothing to tap but the way out. Whatever the piece was offering while it asked --
   "That's the one", "Try the next one" -- is answered and gone the moment it starts working. */
const working = (w: Working) => { acts.value = []; work.value = w; beat.value = 'working' }
function caught(c: Caught) {
  acts.value = []
  got.value = c; name.value = c.name ?? ''; placed.value = ''
  beat.value = 'in'
  refreshFound(); loadHealth()
}
const failed = (text: string, retry = true) => { acts.value = []; wrong.value = { text, retry }; beat.value = 'wrong' }

/* ---- leaving, which is the same word and the same place on every screen ---- */
function notNow() {
  if (props.resume) return void (store.sheet = null)   // a handed-over conversation is the house's; walking away leaves it open
  clear(); where.value = ''; proof.value = null; hint.value = null
  beat.value = 'choose'
  refreshFound()
}
function again() { attempt.value++; clear(); beat.value = 'prove' }

/* ---- beat four ---- */
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
const placed = ref('')
const name = ref('')
const busy = ref(false)
/* A tapped room is placed at once and STAYS ON SCREEN as the chosen one -- it is the undo, and the
   screen it is on is not finished with. Nothing here vanishes under the finger that touched it. */
async function place(id: string) {
  if (!got.value?.device_id || busy.value) return
  busy.value = true
  const was = placed.value
  placed.value = id
  try { await moveDevice(got.value.device_id, id) }
  catch (e: any) { placed.value = was; notify(e.message, 'error') }
  busy.value = false
}
async function done() {
  const g = got.value
  if (g?.device_id && name.value.trim() && name.value.trim() !== g.name) {
    try { await renameDevice(g.device_id, name.value.trim()) } catch (e: any) { notify(e.message, 'error') }
  }
  if (placed.value) notify(`${name.value.trim() || g?.name || 'It'} is in the ${rooms.value.find(r => r.id === placed.value)?.name} now.`)
  notNow()
}
/* An account that brought in six things at once has no one room to be put in. The house does not
   pretend otherwise: it offers the screen that places them, rather than a paragraph about it. */
function intoRooms() { store.goRoom = 'unassigned'; store.sheet = null }

/* What is already waiting is the whole job most of the time, so it is asked for on the way in
   rather than whenever the house next gets round to it. */
onMounted(refreshFound)

/* ?add=switch is the wall handing this job to a phone: the code on the wall opens the house here,
   already at the camera, because the wall has not got one. It arrives mid-conversation on purpose --
   beat one was answered by the person who picked up the phone. */
if (new URLSearchParams(location.search).get('add') === 'switch')
  open_('code', 'switch', 'A switch on the wall')

if (props.resume) open_('signin', props.resume, store.resumeName || 'Sign in again')
</script>

<template>
  <div class="add adding">
    <!-- ===== beat one: what have you got ===== -->
    <template v-if="beat === 'choose'">
      <div class="add-block" v-if="store.found.length || (store.bridge?.waiting ?? 0) > 0">
        <h3 class="label">Already waiting</h3>
        <ul class="found">
          <li v-for="f in store.found" :key="f.flow_id">
            <span class="found-icon"><Icon name="sparkle" :size="18" /></span>
            <span class="found-text"><span class="found-title">{{ f.title }}</span><span class="found-kind">{{ f.kind }}</span></span>
            <button class="button small" @click="open_('signin', f.flow_id, f.title)">Have a look</button>
          </li>
          <li v-if="(store.bridge?.waiting ?? 0) > 0">
            <span class="found-icon"><Icon name="switch" :size="18" /></span>
            <span class="found-text">
              <span class="found-title">{{ store.bridge!.waiting === 1 ? 'A switch is asking to be let in' : `${store.bridge!.waiting} switches are asking to be let in` }}</span>
              <span class="found-kind">Nearby, and not on your house yet</span>
            </span>
            <button class="button small" @click="open_('blink', null, 'A switch on the wall')">Have a look</button>
          </li>
        </ul>
      </div>

      <div class="add-block">
        <h3 class="label">{{ store.found.length ? 'Or start it yourself' : 'What are you adding?' }}</h3>
        <div class="ways">
          <button v-for="d in doors()" :key="d.id" class="way" @click="knock(d)">
            <span class="way-icon"><Icon :name="d.icon" :size="21" /></span>
            <span class="way-text"><span class="way-title">{{ d.title }}</span><span class="way-sub">{{ d.sub }}</span></span>
          </button>
        </div>
      </div>
    </template>

    <!-- ===== beats two, three and four: one shell, and the piece inside it ===== -->
    <div class="flow" v-else>
      <h3 class="flow-title" :class="{ landed: beat === 'in' }">
        <span class="done-icon" v-if="beat === 'in'"><Icon name="check" :size="20" /></span>{{ heading }}
      </h3>

      <!-- the piece draws beat two's middle. It stays mounted while beat three runs: it is the one
           doing the work, and taking it off the screen would cancel what it is waiting on. -->
      <div v-show="beat === 'prove'">
        <component :is="PIECE[proof!]" :key="`${proof}-${attempt}`" :on="hint"
                   @working="working" @caught="caught" @wrong="failed" @acts="(a: Act[]) => acts = a" @head="(h: string) => said = h"
                   @proof="(p: Proof, h: string | null = null) => { proof = p; hint = h; acts = []; said = '' }" />
      </div>

      <!-- beat three -->
      <template v-if="beat === 'working'">
        <div class="bridge-bar"><i style="width: 52%"></i></div>
        <p class="sheet-status" v-if="work?.how_long">{{ work.how_long }}</p>
      </template>

      <!-- beat four -->
      <template v-else-if="beat === 'in'">
        <p class="flow-desc">
          <template v-if="got?.what">It turned out to be <b>{{ got.what }}</b>.</template>
          <template v-else>{{ got?.name || 'It' }} is part of the house now.</template>
        </p>
        <template v-if="got?.device_id">
          <h3 class="label">Which room is it in?</h3>
          <div class="press-rooms">
            <button v-for="r in rooms" :key="r.id" class="chip-btn" :class="{ on: placed === r.id }" @click="place(r.id)">
              <Icon v-if="placed === r.id" name="check" :size="14" />{{ r.name }}
            </button>
          </div>
          <h3 class="label">And what do you call it?</h3>
          <label class="field">
            <input class="input" v-model="name" autocapitalize="words" spellcheck="false" @keydown.enter="done" />
            <span class="field-hint">Named from the room, so most of the time this needs no typing at all.</span>
          </label>
        </template>
        <p class="flow-desc" v-else-if="got?.many">Its things come into the house over the next minute. Any that do not know their room wait under New devices.</p>
      </template>

      <!-- it did not work: one reason, one thing to try, and the way out -->
      <template v-else-if="beat === 'wrong'">
        <p class="flow-desc">{{ wrong?.text }}</p>
      </template>

      <div class="flow-actions">
        <template v-if="beat === 'in'">
          <button class="button" :class="{ busy }" @click="done">Done</button>
          <button class="button ghost" v-if="got?.many" @click="intoRooms">Put them in rooms</button>
          <button class="button ghost" v-else @click="notNow">Add another</button>
        </template>
        <template v-else-if="beat === 'wrong'">
          <button class="button" v-if="wrong?.retry" @click="again">Try again</button>
          <button class="button ghost" @click="notNow">Not now</button>
        </template>
        <template v-else>
          <button v-for="a in acts" :key="a.label" class="button" :class="{ ghost: !a.primary }" @click="a.run()">{{ a.label }}</button>
          <button class="button ghost" @click="notNow">Not now</button>
        </template>
      </div>
    </div>
  </div>
</template>
