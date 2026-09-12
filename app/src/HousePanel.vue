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
import { TONES } from './tone'
import { FACES, LAYOUTS, NAVS } from './layout'
import Icon from './Icon.vue'
import LocationPage from './LocationPage.vue'
import LookPage from './LookPage.vue'
import RoutinesPage from './RoutinesPage.vue'
import PeoplePage from './PeoplePage.vue'
import AddPage from './AddPage.vue'
import HubPage from './HubPage.vue'
import CodePage from './CodePage.vue'
import AdvancedLink from './AdvancedLink.vue'
import { isPage, type PageId } from './pages'

const page = computed<PageId>(() => isPage(store.sheet) ? store.sheet : 'house')
const PAGE: Record<Exclude<PageId, 'house'>, Component> = { location: LocationPage, look: LookPage, routines: RoutinesPage, people: PeoplePage, add: AddPage, hub: HubPage, code: CodePage }

/* a conversation the house already has open (signing an account in again) is
   handed to the Add page on the way in, once, so the page reads as that one job */
const resume = ref<string | null>(null)
watch(page, p => { if (p === 'add') { resume.value = store.resume; store.resume = null } else resume.value = null }, { immediate: true })

const ready = computed(updateReady)
const locked = computed(() => !!store.status?.locked)
const title = computed(() => ({
  house: 'This house', location: 'Where is home?', look: 'How the house looks', routines: 'Routines', people: 'People',
  add: resume.value ? 'Sign in again' : 'Add to the house', hub: 'This hub', code: locked.value ? 'Change the code' : 'Lock the settings',
}[page.value]))

/* each door says where it leads and how things stand there, so most questions
   are answered from the list without opening anything */
const look = computed(() => {
  const l = store.ambient.look
  return [TONES.find(t => t.id === l?.tone)?.label ?? 'Follow the light', LAYOUTS.find(x => x.id === l?.layout)?.label ?? 'Stack', NAVS.find(n => n.id === l?.nav)?.label ?? 'Side', FACES.find(f => f.id === l?.face)?.label ?? 'Paper'].join(' · ')
})
const routines = computed(() => {
  const n = store.routines.length, off = store.routines.filter(r => r.enabled === false).length
  return n ? `${n === 1 ? '1 routine' : `${n} routines`}${off ? `, ${off} off` : ''}` : 'None yet'
})
const people = computed(() => {
  const p = store.presence?.people ?? [], home = p.filter(x => x.home === true).length, phones = store.phones.length
  const who = p.length ? `${p.length === 1 ? '1 person' : `${p.length} people`}, ${home} home` : 'Nobody set up yet'
  return phones ? `${who} · ${phones === 1 ? '1 phone' : `${phones} phones`}` : who
})
const found = computed(() => store.found.length ? `${store.found.length === 1 ? '1 thing' : `${store.found.length} things`} found nearby` : 'Lights, plugs, cameras, locks')
const version = computed(() => { const v = store.status?.version; return !v || v === 'dev' ? 'Development build' : v })
const hub = computed(() => ready.value ? `${version.value} · an update is ready` : version.value)
const code = computed(() => locked.value ? 'Changing the house needs it' : 'Open to anyone on the Wi‑Fi')
const doors = computed(() => [
  { id: 'location' as const, icon: 'pin', name: 'Where home is', hint: store.ambient.location?.name ?? 'Not set yet' },
  { id: 'look' as const, icon: 'sun', name: 'How it looks', hint: look.value },
  { id: 'routines' as const, icon: 'sparkle', name: 'Routines', hint: routines.value },
  { id: 'people' as const, icon: 'people', name: 'People and phones', hint: people.value },
  { id: 'add' as const, icon: 'plus', name: 'Add a device', hint: found.value, attention: store.found.length > 0 },
  { id: 'hub' as const, icon: 'home', name: 'The hub', hint: hub.value, attention: ready.value },
  ...(store.status?.setup_done ? [{ id: 'code' as const, icon: 'lock', name: locked.value ? 'The code' : 'Lock the settings', hint: code.value }] : []),
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
          <button v-for="d in doors" :key="d.id" class="door" :class="{ on: page === d.id, attention: d.attention }" @click="go(d.id)">
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
