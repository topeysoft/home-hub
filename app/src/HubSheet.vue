<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify } from './store'
import { downloadBackup, requestUpdate, removePhone, type Phone } from './api'
import Icon from './Icon.vue'
import Restore from './Restore.vue'
import AdvancedLink from './AdvancedLink.vue'
import PhoneSteps from './PhoneSteps.vue'

/* This hub: which build it is, whether a newer one exists, a backup to take away and a way to put one back. */
const update = computed(() => store.status?.update ?? null)
const busy = ref(false), phone = ref(false), phones = ref(new URLSearchParams(location.search).get('phones') === '1'), sure = ref(''), removing = ref('')   // ?sheet=hub&phones=1 previews the list
/* the phones that belong to the house: who, since when, for how long, and one way out each */
const HOW: Record<string, string> = { code: 'typed the code', wall: 'let in from the wall', setup: 'set up the house' }
const day = (ts: number) => new Date(ts * 1000).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
function phoneLine(p: Phone) {
  const bits = [`${HOW[p.how] ?? 'joined'} ${day(p.joined)}`]
  if (p.expires) bits.push(`until ${day(p.expires)}`)
  return bits.join(' · ')
}
async function remove(p: Phone) {
  if (sure.value !== p.id) { sure.value = p.id; return }         // one tap asks, the second does
  removing.value = p.id
  try { await removePhone(p.id); notify(p.me ? 'This phone is out. Join again from the wall.' : `${p.name} is out.`) }
  catch (e: any) { if (e.message !== 'That needs the code.') notify(e.message, 'error') }
  sure.value = ''; removing.value = ''
}
async function backup() {
  if (busy.value) return
  busy.value = true
  try { await downloadBackup(); notify('Your backup is on its way. Keep it somewhere safe; it holds the house’s keys.') }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = false
}
async function install() {
  try { await requestUpdate(); store.updating = true; notify('Updating. The lights keep working; this screen comes back on its own.') }
  catch (e: any) { notify(e.message, 'error') }
}
const when = (ts?: number | null) => ts ? new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : ''
function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="This hub">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">This hub</h2>
      <p class="sheet-lede">The little computer running the house. It looks after itself; this is where you check on it.</p>

      <ul class="hub-rows">
        <li>
          <span class="hub-k">Software</span>
          <span class="hub-v">{{ !store.status?.version || store.status.version === 'dev' ? 'Development build' : store.status.version }}<span class="hub-sub" v-if="update?.checked"> · checked {{ when(update.checked) }}</span></span>
          <button class="button small" v-if="update?.available && !store.updating && !update.requested" @click="install">Install the update</button>
          <span class="hub-sub" v-else-if="store.updating || update?.requested || update?.state?.state === 'running'">Updating…</span>
          <span class="hub-sub" v-else-if="update?.available === false">Up to date</span>
          <span class="hub-sub" v-else-if="update?.error">Couldn't check: no internet?</span>
          <span v-else></span>
        </li>
        <li>
          <span class="hub-k">Backup</span>
          <span class="hub-v">Settings, rooms, routines, the engine's setup and the radios' keys, in one file.<span class="hub-sub"> It holds the house's keys: keep it private.</span></span>
          <button class="button small" :class="{ busy }" @click="backup">{{ busy ? 'Packing…' : 'Back up' }}</button>
        </li>
        <li>
          <span class="hub-k">Phone</span>
          <span class="hub-v">The same house on a phone, as an app on its first screen.</span>
          <button class="button small" @click="phone = !phone">{{ phone ? 'Hide' : 'Show how' }}</button>
        </li>
        <li class="hub-wide" v-if="phone"><PhoneSteps /></li>
        <li v-if="store.status?.locked">
          <span class="hub-k">Phones</span>
          <span class="hub-v">{{ store.phones.length === 1 ? 'One phone belongs' : `${store.phones.length} phones belong` }} to the house. Each runs it from the Wi‑Fi; none reaches it from outside yet.<span class="hub-sub"> A phone that is removed is out at once.</span></span>
          <button class="button small" @click="phones = !phones">{{ phones ? 'Hide' : 'See them' }}</button>
        </li>
        <li v-else-if="store.status?.setup_done">
          <span class="hub-k">Phones</span>
          <span class="hub-v">Without a code, every phone on the Wi‑Fi can run the house.<span class="hub-sub"> Set one and only the phones you let in can.</span></span>
          <button class="button small" @click="store.sheet = 'code'">Set a code</button>
        </li>
        <li class="hub-wide" v-if="phones && store.status?.locked">
          <ul class="phones">
            <li v-for="p in store.phones" :key="p.id">
              <span class="phones-icon"><Icon :name="p.kind === 'wall' ? 'home' : 'phone'" :size="16" /></span>
              <span class="phones-text"><span class="phones-name">{{ p.name }}<span class="phones-me" v-if="p.me"> · this one</span></span><span class="phones-sub">{{ phoneLine(p) }}</span></span>
              <button class="button small ghost" :class="{ busy: removing === p.id, warn: sure === p.id }" @click="remove(p)">{{ sure === p.id ? (p.me ? 'Remove this one?' : 'Sure?') : 'Remove' }}</button>
            </li>
          </ul>
        </li>
        <li>
          <span class="hub-k">Restore</span>
          <span class="hub-v">Put a backup back, here or on a new hub. Everything running now is replaced by what is in the file.</span>
          <Restore small />
        </li>
      </ul>
      <AdvancedLink />
    </div>
  </div>
</template>
