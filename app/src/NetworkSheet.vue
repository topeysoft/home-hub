<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify, refreshBridge } from './store'
import { getNetwork, scanNetworks, moveBridges, moveHub, networkDone, type NetState, type SeenNetwork } from './api'
import Icon from './Icon.vue'

/*
 * Changing the network the house runs on.
 *
 * Drawn from design/network/ -- Which (the choice, and what moves with it), Moving (one bridge at a
 * time, by room), Followed and Behind (the two endings). The argument is docs/network.md.
 *
 * The thing this sheet must never do is let somebody think they are changing a setting on one box.
 * On most hubs this is a change to twelve things: the hub on its cable stays where it is and eleven
 * bridges move, or the hub moves and takes them with it. So the consequence is said in the lede,
 * before the list of networks -- putting it after the choice would be a small dishonesty about what
 * the button does.
 *
 * Everything it draws is the brain's. Which networks are in the air, who followed and who did not,
 * and whether this hub can change its own connection at all are facts about this house that a panel
 * would only be guessing at.
 */
const emit = defineEmits<{ (e: 'close'): void }>()

const net = ref<NetState | null>(null)
const seen = ref<SeenNetwork[]>([])
const scanning = ref(false)
const busy = ref(false)
const ssid = ref('')
const password = ref('')
const typing = ref(false)          // no radio to scan with, or somebody wants a network that is not listed

/* A move in flight, from whichever side is carrying it. The bridges' journey rides along on the
   bridge status the panel already polls every two seconds, so this needs no clock of its own. */
const move = computed(() => store.bridge?.moving ?? net.value?.bridges_moving ?? null)
/* Does this change the hub as well? Only when the hub is itself on the Wi-Fi -- a hub on a cable is
   not moved by changing what its bridges use, and saying otherwise would frighten people out of a
   change that cannot touch them. */
const hubMoves = computed(() => net.value?.how === 'wifi' || net.value?.how === 'none')
const bridges = computed(() => net.value?.bridges.count ?? 0)
const them = computed(() => bridges.value === 1 ? 'your bridge' : `your ${bridges.value} bridges`)

const TITLE = computed(() => {
  const m = move.value
  if (m?.state === 'moving') return 'Moving them over.'
  if (m?.state === 'done') return m.late?.length
    ? `${m.followed.length === 1 ? 'One' : m.followed.length} followed. ${m.late.length === 1 ? 'One didn’t' : `${m.late.length} didn’t`}.`
    : m.total === 0 ? 'That’s set.' : `All ${m.total} followed.`
  return 'Which Wi‑Fi?'
})

async function load() {
  try { net.value = await getNetwork() } catch (e: any) { notify(e.message, 'error') }
  // A hub with no radio has nothing to scan with, so it goes straight to the two fields rather than
  // showing an empty list and a spinner that will never finish.
  if (net.value && !net.value.can_change) typing.value = true
  else scan()
}
async function scan() {
  if (scanning.value) return
  scanning.value = true
  try { seen.value = (await scanNetworks()).networks }
  catch { /* the row below still lets somebody type one */ }
  scanning.value = false
}
function pick(n: SeenNetwork) {
  ssid.value = n.ssid
  password.value = ''
  if (!n.secure) go()
}
/* The hub is told LAST and the bridges first, and that order is the brain's -- POST /network/hub does
   both in one call for exactly that reason. This only chooses which question is being asked. */
async function go() {
  if (busy.value || !ssid.value.trim()) return notify('Which Wi‑Fi? The name is needed.', 'error')
  busy.value = true
  try {
    // Drawn from the answer to this very call, so the sheet changes under the tap rather than at the
    // next poll. The polling below is what keeps it moving afterwards.
    if (hubMoves.value) { net.value = await moveHub(ssid.value.trim(), password.value) }
    else if (net.value) { net.value = { ...net.value, bridges_moving: await moveBridges(ssid.value.trim(), password.value) } }
    refreshBridge()
  } catch (e: any) { notify(e.message, 'error') }
  busy.value = false
}
async function done() {
  try { store.bridge = await networkDone() } catch { /* it clears itself on the next poll */ }
  emit('close')
}

/* Eleven rows is a sheet that fills a wall and overflows a phone, and nobody reads the eleventh. Six,
   then a count -- the same shape design/network/Moving.dc.html draws. What is shown is the front of
   the queue: the ones that just came back and the ones going next, which is where the eye already is.
   The bar and the count above carry the whole picture. */
const SHOW = 6
const shown = computed(() => {
  const m = move.value
  if (!m) return { rows: [] as { where: string; done: boolean }[], more: 0 }
  const rows = [...m.followed.map(w => ({ where: w, done: true })),
                ...(m.waiting ?? []).map(w => ({ where: w, done: false }))]
  return { rows: rows.slice(0, SHOW), more: Math.max(0, rows.length - SHOW) }
})

const SIGNAL: Record<string, string> = { strong: 'Strong', ok: 'Good', faint: 'Faint from here' }
/* Three aerials, so the list answers "which of these can the hub actually reach" at a glance rather
   than only in words a metre away from the wall. */
const bars = (s?: string) => s === 'strong' ? 'wifi' : s === 'ok' ? 'wifi-mid' : 'wifi-low'
const where = (n: SeenNetwork) => [SIGNAL[n.signal ?? ''] ?? '', n.band ? `${n.band} GHz` : ''].filter(Boolean).join(' · ')
const onNow = computed(() => net.value?.bridges.ssid || '')

function key(e: KeyboardEvent) { if (e.key === 'Escape' && move.value?.state !== 'moving') emit('close') }
onMounted(() => { window.addEventListener('keydown', key); load() })
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="move?.state === 'moving' || emit('close')">
    <div class="sheet" role="dialog" :aria-label="TITLE">
      <div class="sheet-head">
        <h2 class="display">{{ TITLE }}</h2>
        <button class="round sheet-close" v-if="move?.state !== 'moving'" @click="emit('close')" aria-label="Close"><Icon name="close" :size="20" /></button>
      </div>
      <div class="sheet-body">

        <!-- ============ choosing. The consequence comes before the list. ============ -->
        <template v-if="!move">
          <p class="sheet-lede" v-if="!bridges && !hubMoves">
            This is the Wi‑Fi the hub gives to any bridge it sets up. The hub itself is on a cable and stays on it.
          </p>
          <p class="sheet-lede" v-else-if="net?.how === 'cable'">
            The hub is on a cable and stays on it. This is the Wi‑Fi {{ them }} use — change it here and they all move over together.
          </p>
          <!-- A hub whose machine has no network script. Its own connection is somebody else's
               business and this sheet must not imply it is about to touch it. -->
          <p class="sheet-lede" v-else>
            This hub’s own connection is looked after by the machine it runs on. What this changes is the Wi‑Fi {{ them }} use — change it here and they all move over together.
          </p>
          <p class="sheet-lede" v-else>
            This moves the hub itself{{ bridges ? `, and takes ${them} with it` : '' }}. It tells them first, so nothing is left behind on the old network.
          </p>

          <ul class="nets" v-if="!typing">
            <li v-if="onNow" class="net here">
              <!-- Full bars, always. This row is what the bridges are on, and the hub has no idea how
                   well THEY hear it -- drawing a strength here would be an invented number. -->
              <Icon name="wifi" :size="20" />
              <span class="bridge-text"><span class="bridge-name">{{ onNow }}</span><span class="bridge-sub">{{ hubMoves ? 'What the house is on now' : 'What they use now' }}</span></span>
              <span class="bridge-sub">In use</span>
            </li>
            <template v-for="n in seen" :key="n.ssid">
              <li v-if="n.ssid !== onNow" class="net" :class="{ pick: n.ssid === ssid }" role="button" tabindex="0" @click="pick(n)" @keydown.enter="pick(n)">
                <Icon :name="bars(n.signal)" :size="20" />
                <span class="bridge-text"><span class="bridge-name">{{ n.ssid }}</span><span class="bridge-sub">{{ where(n) }}</span></span>
                <span class="net-tick" v-if="n.ssid === ssid"><Icon name="check" :size="12" /></span>
                <span v-else></span>
              </li>
              <!-- the password opens under the network it belongs to. There is no second decision,
                   so there is no second screen. -->
              <li v-if="n.ssid === ssid && n.secure" class="net-pass">
                <label class="field"><span class="field-label">Password</span>
                  <input class="input" type="password" v-model="password" autocomplete="off" @keydown.enter="go" />
                </label>
              </li>
            </template>
            <li v-if="scanning" class="bridge-sub scan-note"><span class="pulse-dot"></span> Looking…</li>
            <li v-else-if="!seen.length" class="bridge-sub scan-note">Nothing else in the air here.</li>
          </ul>

          <template v-else>
            <label class="field"><span class="field-label">Wi‑Fi name</span>
              <input class="input" v-model="ssid" autocomplete="off" autocapitalize="off" spellcheck="false" @keydown.enter="go" /></label>
            <label class="field"><span class="field-label">Password</span>
              <input class="input" type="password" v-model="password" autocomplete="off" @keydown.enter="go" /></label>
          </template>

          <!-- The row that makes the button safe to press. Not reassurance: a property of the
               firmware, and the reason two keys exist at all (docs/network.md, piece 3). -->
          <div class="bridge-row" v-if="bridges">
            <span class="bridge-icon"><Icon name="refresh" :size="18" /></span>
            <span class="bridge-text">
              <span class="bridge-name">If it’s the wrong password, nothing breaks</span>
              <span class="bridge-sub">Every bridge keeps the old one as well. Anything that can’t get on the new network is back on <b>{{ onNow || 'the old one' }}</b> within a few minutes, by itself.</span>
            </span>
          </div>
          <!-- ...and the one that says what it cannot promise. The hub moving is the only part of
               this that can end with nothing able to reach it. -->
          <div class="bridge-row" v-if="hubMoves">
            <span class="bridge-icon"><Icon name="clock" :size="18" /></span>
            <span class="bridge-text">
              <span class="bridge-name">If the hub can’t get on, it comes back</span>
              <span class="bridge-sub">It gives the new network three minutes to answer and puts the old one back if it doesn’t. This screen goes quiet while that happens.</span>
            </span>
          </div>

          <!-- A network that is not in the list -- hidden, or too faint to have been seen -- is a real
               case and a rare one, so it is a quiet line rather than a third button competing with
               the two that matter. -->
          <button class="as-link" v-if="!typing" @click="typing = true">My Wi‑Fi isn’t listed</button>

          <div class="flow-actions">
            <!-- Nothing to press until something is chosen: a primary button that answers a tap with
                 an error message is a button that has been left switched on by mistake. -->
            <button class="button" :class="{ busy }" :disabled="!ssid.trim()" @click="go">{{ hubMoves ? 'Move the house over' : bridges ? 'Move them over' : 'Use it' }}</button>
            <button class="button ghost" @click="emit('close')">Not now</button>
          </div>
        </template>

        <!-- ============ the move. By room, never by chip. ============ -->
        <template v-else-if="move.state === 'moving'">
          <p class="sheet-lede">Each one takes the new Wi‑Fi, restarts, and comes back on it. A couple of minutes for all {{ move.total }}. You can walk away — the wall will say how it went.</p>
          <div class="bridge-bar"><i :style="{ width: `${Math.round((move.followed.length / Math.max(1, move.total)) * 100)}%` }"></i></div>
          <p class="bridge-sub count">{{ move.followed.length }} of {{ move.total }} {{ move.followed.length === 1 ? 'is' : 'are' }} back</p>
          <ul class="movers">
            <li v-for="r in shown.rows" :key="r.where">
              <span class="tick" :class="{ done: r.done }"><Icon v-if="r.done" name="check" :size="12" /></span>
              <span class="bridge-name">{{ r.where }}</span>
              <span class="bridge-sub">{{ r.done ? `Back on ${move.ssid}` : 'Waiting its turn' }}</span>
            </li>
            <li v-if="shown.more" class="more"><span></span><span class="bridge-sub">and {{ shown.more }} more</span></li>
          </ul>
          <div class="bridge-row">
            <span class="bridge-icon"><Icon name="light" :size="18" /></span>
            <span class="bridge-text">
              <span class="bridge-name">Your switches keep working</span>
              <span class="bridge-sub">The switches on the wall talk to each other directly, so the lights are unaffected by any of this. What pauses is the panel’s view of them, one bridge at a time.</span>
            </span>
          </div>
        </template>

        <!-- ============ the two endings ============ -->
        <template v-else>
          <template v-if="!move.late?.length">
            <p class="flow-done">
              <span class="done-icon"><Icon name="check" :size="20" /></span>
              <span v-if="move.total">Every bridge is on <b>{{ move.ssid }}</b> and talking to the hub. Nothing else to do.</span>
              <span v-else>That’s what any bridge set up from now on will be given.</span>
            </p>
            <div class="bridge-row" v-if="move.total">
              <span class="bridge-icon good"><Icon name="check" :size="18" /></span>
              <span class="bridge-text">
                <span class="bridge-name">They kept the old Wi‑Fi for now</span>
                <span class="bridge-sub">Just in case. The hub takes it off them once it’s sure of the new one. You don’t have to do anything.</span>
              </span>
            </div>
          </template>
          <template v-else>
            <p class="sheet-lede">{{ move.late.length === 1 ? 'This one was' : 'These were' }} not switched on when the others moved, so {{ move.late.length === 1 ? 'it is' : 'they are' }} still looking for the old Wi‑Fi:</p>
            <ul class="late">
              <li v-for="w in move.late" :key="w"><Icon name="alert" :size="18" /><span class="bridge-name">{{ w }}</span></li>
            </ul>
            <div class="bridge-row">
              <span class="bridge-icon good"><Icon name="light" :size="18" /></span>
              <span class="bridge-text">
                <span class="bridge-name">The lights in those rooms still work</span>
                <span class="bridge-sub">Those switches don’t need the bridge to turn each other on. What the house has lost is being able to see them from here.</span>
              </span>
            </div>
            <div class="bridge-row">
              <span class="bridge-icon"><Icon name="power" :size="18" /></span>
              <span class="bridge-text">
                <span class="bridge-name">Bring each one to the hub and plug it in</span>
                <span class="bridge-sub">A minute each, and they go straight back where they were.</span>
              </span>
            </div>
          </template>
          <div class="flow-actions"><button class="button" @click="done">{{ move.late?.length ? 'OK' : 'Done' }}</button></div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The networks in the air. A row is the same object the Add screen draws for a found thing, so this
   only says what is different: the one in use is quiet, and the chosen one is lit. */
.nets { list-style: none; margin: 0 0 4px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.net {
  display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px;
  padding: 11px 14px; border-radius: 16px;
  background: var(--surface); border: 1px solid var(--edge); cursor: pointer;
}
.net.here { opacity: 0.55; cursor: default; }
.net.pick { border-color: color-mix(in srgb, var(--lamp) 45%, transparent); background: color-mix(in srgb, var(--lamp) 10%, var(--surface)); }
.net-tick {
  width: 22px; height: 22px; border-radius: 999px; display: grid; place-items: center;
  background: var(--lamp); color: var(--lamp-ink);
}
.net-pass { margin: 2px 0 4px; }
.net-pass .field { margin: 0; }
.scan-note { display: flex; align-items: center; gap: 8px; padding: 6px 2px; }
/* The way out of the list, said quietly. */
.as-link {
  display: block; margin: 2px 0 14px; padding: 0;
  background: none; border: 0; color: var(--ink-2); font: inherit; font-size: 13.5px;
  text-decoration: underline; text-underline-offset: 3px; cursor: pointer;
}
.as-link:hover { color: var(--ink); }

/* One bridge on its way, named by the room it serves. Three columns so the state reads down the
   right edge rather than hiding at the end of each line. */
.movers { list-style: none; margin: 0 0 14px; padding: 0; }
.movers li { display: grid; grid-template-columns: 24px 1fr auto; align-items: center; gap: 12px; padding: 9px 2px; }
.movers li + li { border-top: 1px solid color-mix(in srgb, var(--edge) 55%, transparent); }
.tick { width: 21px; height: 21px; border-radius: 999px; display: grid; place-items: center; border: 1.5px solid var(--edge-hi); }
.tick.done { background: var(--live); color: #0b2216; border-color: transparent; }
.count { margin: 6px 0 16px; }
.movers li.more { grid-template-columns: 24px 1fr; border-top: 0; padding-top: 12px; }

/* The ones that did not follow: amber, not red. Nothing is broken -- the lights in those rooms still
   work, and the sheet says so directly underneath. */
.late { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 7px; }
.late li {
  display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 12px;
  padding: 11px 14px; border-radius: 15px; color: var(--lamp);
  border: 1px solid color-mix(in srgb, var(--lamp) 32%, transparent);
  background: color-mix(in srgb, var(--lamp) 9%, var(--surface));
}
.late .bridge-name { color: var(--ink); }
</style>
