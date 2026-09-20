<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * This house: the one door to everything that is not turning something on or
 * off, as one panel. It rises the way an opened device does -- the home recedes
 * behind it -- and inside it is split the way a tablet's settings are: the
 * doors down the left, always in view; the page on the right, the only thing
 * that scrolls. The title and the close never move, and there is no way back
 * to lose, because the list never left.
 *
 * On a phone the same panel is the whole screen: the list first, a page in
 * front of it with a back arrow. One component, one breakpoint (panel.css).
 *
 * The pages were once separate sheets, each a card floating in the middle of
 * a 1440px wall with its own close button that scrolled away with the content.
 * They kept their code; only the frame changed.
 */
import { computed, onMounted, onUnmounted, ref, watch, type Component } from 'vue'
import { store, updateReady } from './store'
import { adjusted, feelFrom } from './look'
import Icon from './Icon.vue'
import LocationPage from './LocationPage.vue'
import LookPage from './LookPage.vue'
import RoutinesPage from './RoutinesPage.vue'
import PeoplePage from './PeoplePage.vue'
import AccountsPage from './AccountsPage.vue'
import AddPage from './AddPage.vue'
import SharePage from './SharePage.vue'
import HubPage from './HubPage.vue'
import CodePage from './CodePage.vue'
import NotesPage from './NotesPage.vue'
import HappenedPage from './HappenedPage.vue'
import ChangesPage from './ChangesPage.vue'
import AdvancedLink from './AdvancedLink.vue'
import { isPage, LIT, type PageId } from './pages'

const page = computed<PageId>(() => isPage(store.sheet) ? store.sheet : 'house')
const PAGE: Record<Exclude<PageId, 'house'>, Component> = { location: LocationPage, look: LookPage, routines: RoutinesPage, people: PeoplePage, accounts: AccountsPage, add: AddPage, share: SharePage, hub: HubPage, code: CodePage, notes: NotesPage, happened: HappenedPage, changes: ChangesPage }

/* a conversation the house already has open (signing an account in again) is
   handed to the Add page on the way in, once, so the page reads as that one job */
const resume = ref<string | null>(null)
watch(page, p => { if (p === 'add') { resume.value = store.resume; store.resume = null } else resume.value = null }, { immediate: true })

const ready = computed(updateReady)
const locked = computed(() => !!store.status?.locked)
const title = computed(() => ({
  house: 'This house', location: 'Where is home?', look: 'How the house looks', routines: 'Routines', people: 'People', accounts: 'Accounts',
  add: resume.value ? 'Sign in again' : 'Add to the house', share: 'Share this house', hub: 'This hub', code: locked.value ? 'Change the code' : 'Lock the settings',
  notes: 'Needs a look', happened: 'What happened', changes: 'Who changed what',
}[page.value]))

/* Which door is lit. Who changed what has no door of its own -- it is reached from inside What
   happened -- so the door it belongs to stays lit while it is open, and the list never looks as
   though nothing in it is selected. */
const lit = computed<PageId>(() => LIT[page.value] ?? page.value)

/* each door says where it leads and how things stand there, so most questions
   are answered from the list without opening anything */
/* One feel, not four dials. The old line read "Follow the light · Stack · Side ·
   Paper", which is four answers to a question nobody asked and, since the
   arrangement went automatic, one of them was a guess: it said Stack on a wall
   panel laying itself out as a wall. A door says where it leads. */
const look = computed(() => feelFrom(store.ambient.look).label + (adjusted(store.ambient.look) ? ', adjusted' : ''))
const routines = computed(() => {
  const n = store.routines.length, off = store.routines.filter(r => r.enabled === false).length
  return n ? `${n === 1 ? '1 routine' : `${n} routines`}${off ? `, ${off} off` : ''}` : 'None yet'
})
const people = computed(() => {
  const p = store.presence?.people ?? [], home = p.filter(x => x.home === true).length, phones = store.phones.length
  const who = p.length ? `${p.length === 1 ? '1 person' : `${p.length} people`}, ${home} home` : 'Nobody set up yet'
  return phones ? `${who} · ${phones === 1 ? '1 phone' : `${phones} phones`}` : who
})
/* the door answers the question the page exists for: is anything waiting on a person? */
const accounts = computed(() => {
  const a = store.accounts, want = a.filter(x => x.state !== 'on')
  if (!a.length) return 'Nothing signed in yet'
  if (!want.length) return a.length === 1 ? '1 account, signed in' : `${a.length} accounts, all signed in`
  return want.length === 1 ? `${want[0].name} ${want[0].state === 'signin' ? 'needs signing in' : 'is not answering'}` : `${want.length} need a look`
})
const found = computed(() => store.found.length ? `${store.found.length === 1 ? '1 thing' : `${store.found.length} things`} found nearby` : 'Lights, plugs, cameras, locks')
/* The one door that says what it WORKS WITH rather than how it stands, until it is on. Nobody knows
   they can do this, so the hint is the advertisement: naming the apps is what makes somebody open it.
   Once it is shared the hint becomes the state, which is what every other door does. */
const share = computed(() => {
  const s = store.share
  /* Off, the hint is the three names and nothing else. The count belongs here too and does not fit:
     a door's hint is one line that ellipsises, and "9 things ready · Apple Home, Google Ho…" loses
     the third name, which is the one word that might be the reason somebody opens this. */
  if (!s || !s.ready || !s.on) return 'Apple Home, Google Home, Alexa'
  const things = s.shared === 1 ? '1 thing' : `${s.shared} things`
  return s.holders.length ? `${things}, with ${s.holders.map(h => h.name).join(' and ')}` : `${things} ready to add`
})
const version = computed(() => { const v = store.status?.version; return !v || v === 'dev' ? 'Development build' : v })
const hub = computed(() => ready.value ? `${version.value} · an update is ready` : version.value)
const code = computed(() => locked.value ? 'Changing the house needs it' : 'Open to anyone on the Wi‑Fi')
const notes = computed(() => store.notes.length === 1 ? store.notes[0].text : `${store.notes.length} things have stopped answering`)
/* The brain writes this line too. It has to say what is actually inside, and "2 things still on"
   versus "2 things still unlocked" is a distinction the panel cannot make from a count. */
const happened = computed(() => store.happened?.hint ?? 'What the house did while you were out')
const doors = computed(() => [
  { id: 'location' as const, icon: 'pin', name: 'Where home is', hint: store.ambient.location?.name ?? 'Not set yet' },
  { id: 'look' as const, icon: 'sun', name: 'How it looks', hint: look.value },
  { id: 'routines' as const, icon: 'sparkle', name: 'Routines', hint: routines.value },
  { id: 'people' as const, icon: 'people', name: 'People and phones', hint: people.value },
  { id: 'accounts' as const, icon: 'lock', name: 'Accounts', hint: accounts.value, attention: store.accounts.some(a => a.state !== 'on') },
  { id: 'add' as const, icon: 'plus', name: 'Add to the house', hint: found.value, attention: store.found.length > 0 },
  { id: 'share' as const, icon: 'share', name: 'Share this house', hint: share.value },
  { id: 'hub' as const, icon: 'home', name: 'The hub', hint: hub.value, attention: ready.value },
  /* Always here, unlike Needs a look: this is a place somebody goes to look something up, not a
     fault that should appear only when there is one. */
  { id: 'happened' as const, icon: 'clock', name: 'What happened', hint: happened.value },
  ...(store.status?.setup_done ? [{ id: 'code' as const, icon: 'lock', name: locked.value ? 'The code' : 'Lock the settings', hint: code.value }] : []),
  /* only while there is something behind it. A door that is always there saying "nothing is wrong"
     teaches a person to stop reading it, which is the opposite of what a fault list is for. */
  ...(store.notes.length ? [{ id: 'notes' as const, icon: 'sparkle', name: 'Needs a look', hint: notes.value, attention: true }] : []),
])

/* the front page: the house at a glance, and the one line for the curious */
const homeLine = computed(() => {
  const p = store.presence?.people ?? [], home = p.filter(x => x.home === true).map(x => x.name)
  if (!p.length) return ''
  if (!home.length) return 'Nobody home'
  if (home.length === p.length) return 'Everyone home'
  return home.length === 1 ? `${home[0]} is home` : `${home.slice(0, -1).join(', ')} and ${home[home.length - 1]} are home`
})

function go(id: PageId) { store.sheet = id }
function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="house" :class="{ 'at-doors': page === 'house' }" role="dialog" aria-label="This house">
    <div class="house-veil" @click="close"></div>
    <div class="house-panel">
      <aside class="house-doors">
        <div class="house-doors-head">
          <span class="house-doors-title display">This house</span>
          <button class="round house-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
        </div>
        <nav class="doors" aria-label="Pages">
          <button v-for="d in doors" :key="d.id" class="door" :class="{ on: lit === d.id, attention: d.attention }" @click="go(d.id)">
            <span class="door-icon"><Icon :name="d.icon" :size="18" /></span>
            <span class="door-text"><span class="door-name">{{ d.name }}</span><span class="door-hint">{{ d.hint }}</span></span>
            <Icon name="back" :size="16" class="flip" />
          </button>
        </nav>
        <p class="house-foot"><span class="link" :class="{ up: store.linkUp }">{{ store.linkUp ? 'Connected' : 'Reconnecting' }}</span></p>
      </aside>

      <section class="house-main">
        <header class="house-head">
          <button class="round house-back" @click="go('house')" aria-label="Back to This house"><Icon name="back" :size="20" /></button>
          <h2 class="display">{{ title }}</h2>
          <button class="round house-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
        </header>
        <Transition name="view" mode="out-in">
          <div class="house-page" :key="page">
            <div class="page" v-if="page === 'house'">
              <p class="page-lede">Everything about the house that is not a light, a scene or a door. Those never need the code; some of this does.</p>
              <ul class="hub-rows">
                <li><span class="hub-k">Home</span><span class="hub-v">{{ store.ambient.location?.name ?? 'No location yet' }}<span class="hub-sub" v-if="homeLine"> · {{ homeLine }}</span></span><button class="button small ghost" @click="go(store.ambient.location ? 'people' : 'location')">{{ store.ambient.location ? 'People' : 'Set it' }}</button></li>
                <li><span class="hub-k">Software</span><span class="hub-v">{{ version }}<span class="hub-sub" v-if="ready"> · an update is ready</span></span><button class="button small" :class="{ ghost: !ready }" @click="go('hub')">{{ ready ? 'Update' : 'The hub' }}</button></li>
                <li><span class="hub-k">Settings</span><span class="hub-v">{{ locked ? 'Locked. Changing the house needs the code.' : 'Open. Anyone on the Wi‑Fi can change the house.' }}</span><button class="button small" :class="{ ghost: locked }" v-if="store.status?.setup_done" @click="go('code')">{{ locked ? 'The code' : 'Lock' }}</button><span v-else></span></li>
              </ul>
              <AdvancedLink />
            </div>
            <component v-else :is="PAGE[page]" :resume="resume" :class="'page-' + page" />
          </div>
        </Transition>
      </section>
    </div>
  </div>
</template>
