<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify, refreshBridge } from './store'
import { adoptBridge, dismissBridge, placedBridge, bridgeWifi, BRIDGE_STEPS } from './api'
import Icon from './Icon.vue'
import BridgeArt from './BridgeArt.vue'

/*
 * Setting up a bridge, on the wall.
 *
 * One sheet for the whole job because it IS one job, and the person is standing there for all of it.
 * It opens itself: a bridge knocking or being written to is something that happened in the room, not
 * somewhere you navigate to. Drawn from design/puck/ -- Knock (it arrives over the air), Cable (it
 * arrives on the hub's lead), Placing (the walk to find it a socket).
 *
 * The one thing this screen must never do is decide. Whether a bridge is offering itself, how far it
 * has got, and how many switches it can hear are all the brain's to say; the panel draws the state
 * it is given and sends back the two answers a person can give -- yes that is mine, and leave it here.
 */
const b = computed(() => store.bridge)
const busy = ref(false)

const TITLE: Record<string, string> = {
  knocking: 'A bridge is here.',
  working: 'Setting up the bridge.',
  placing: 'Now find it a home.',
  ready: 'It’s in.',
  failed: 'That did not work.',
  wifi: 'One thing it needs.',
}
const title = computed(() => b.value?.needs === 'wifi' ? TITLE.wifi : TITLE[b.value?.state ?? ''] ?? 'A bridge')

/* the three things that go on it, in the order they go on. The brain names the one that is live and
   everything before it is done -- so the panel never has to keep its own idea of progress. */
const STEPS = { software: 'Giving it its software', wifi: 'Putting it on your Wi‑Fi', keys: 'Handing it the keys to your switches' }
const at = computed(() => BRIDGE_STEPS.indexOf((b.value?.step ?? 'software') as any))
const steps = computed(() => BRIDGE_STEPS.map((id, i) => ({ id, text: STEPS[id], done: i < at.value, live: i === at.value })))
const far = computed(() => `${Math.round(((at.value + 0.5) / BRIDGE_STEPS.length) * 100)}%`)

/* what the light on it is saying, which is the same three words the firmware has. Amber while it is
   looking, green once it can hear switches, red when it is too far to hear any. */
const LIGHTS = [
  { light: 'amber' as const, name: 'Blinking amber', sub: 'Looking for your switches' },
  { light: 'green' as const, name: 'Steady green', sub: 'It can hear them. Leave it there.' },
  { light: 'red' as const, name: 'Breathing red', sub: 'Too far. Try a socket nearer a switch.' },
]
const heard = computed(() => {
  const n = b.value?.switches ?? 0
  if (!n) return 'Nothing yet'
  return n === 1 ? 'Hears 1 switch' : `Hears ${n} switches`
})

async function run(fn: () => Promise<any>, after?: string) {
  if (busy.value) return
  busy.value = true
  try { store.bridge = await fn(); if (after) notify(after) }
  catch (e: any) { notify(e.message, 'error') }
  busy.value = false
  refreshBridge()
}
/* The one thing a hub on a cable cannot know: the house's Wi-Fi. Asked here, once, and kept -- the
   job picks up where it stopped, on the same cable, and no bridge after this one asks again. */
const ssid = ref(''), password = ref('')
const tell = () => { if (!ssid.value.trim()) return notify('Which Wi-Fi? The name is needed.', 'error'); run(() => bridgeWifi(ssid.value.trim(), password.value)) }
const adopt = () => run(adoptBridge)
const dismiss = () => run(dismissBridge)
const placed = () => run(placedBridge)
/* Walking away from a bridge that is mid-job does not stop it -- the hub is writing to a thing on its
   own cable and will finish whatever this screen does. Closing only puts the sheet away; it comes
   back on the next poll while there is still something to say. */
function close() { if (store.bridge) store.bridge = { ...store.bridge, state: 'none' } }
function key(e: KeyboardEvent) { if (e.key === 'Escape' && b.value?.state !== 'working') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" v-if="b" @click.self="b.state === 'working' || close()">
    <div class="sheet bridge" role="dialog" :aria-label="title">
      <div class="sheet-head">
        <h2 class="display">{{ title }}</h2>
        <button class="round sheet-close" v-if="b.state !== 'working'" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      </div>
      <div class="sheet-body">

        <!-- it arrived on its own and is blinking. Nothing of the house's has gone anywhere yet. -->
        <template v-if="b.state === 'knocking'">
          <p class="sheet-lede">Something was plugged in nearby a moment ago. A bridge brings in the wall switches that have no Wi‑Fi of their own — the ones already in your walls.</p>
          <div class="bridge-stage">
            <BridgeArt light="amber" />
            <span class="bridge-caption"><span class="pulse-dot"></span>It is blinking amber right now</span>
          </div>
          <div class="bridge-row">
            <span class="bridge-icon"><Icon name="lock" :size="18" /></span>
            <span class="bridge-text"><span class="bridge-name">Nothing has been let in yet</span><span class="bridge-sub">Until you say yes it is only knocking. Nothing of yours is on it.</span></span>
          </div>
          <div class="flow-actions">
            <button class="button" :class="{ busy }" @click="adopt">Yes, that’s mine</button>
            <button class="button ghost" @click="dismiss">Not mine</button>
          </div>
        </template>

        <!-- the hub is writing to it. There is nothing to do, so there is nothing to press. -->
        <template v-else-if="b.state === 'working'">
          <p class="sheet-lede" v-if="b.how === 'cable'">It is on the hub’s cable, so everything it needs is going on it now. About a minute. You can walk away; the wall will say when it is done.</p>
          <p class="sheet-lede" v-else>Everything it needs is going on it now. About a minute. You can walk away; the wall will say when it is done.</p>
          <div class="bridge-stage wide" v-if="b.how === 'cable'">
            <BridgeArt scene="cable" />
            <span class="bridge-label left">the bridge</span>
            <span class="bridge-label right">the hub</span>
          </div>
          <div class="bridge-stage" v-else><BridgeArt light="amber" /></div>
          <div class="bridge-bar"><i :style="{ width: far }"></i></div>
          <ul class="bridge-steps">
            <li v-for="s in steps" :key="s.id" :class="{ done: s.done, live: s.live }">
              <span class="bridge-tick"><Icon v-if="s.done" name="check" :size="13" /><span v-else-if="s.live" class="pulse-dot"></span></span>
              <span>{{ s.text }}</span>
            </li>
          </ul>
          <div class="bridge-row">
            <span class="bridge-icon"><Icon name="clock" :size="18" /></span>
            <span class="bridge-text"><span class="bridge-name">Nothing to type</span><span class="bridge-sub">No app, no password screen, no code on the box. The hub already knows all of it.</span></span>
          </div>
        </template>

        <!-- the walk. The wall cannot follow, so what it hands over is how to read the thing itself. -->
        <template v-else-if="b.state === 'placing'">
          <p class="sheet-lede">Unplug it and put it on any charger near one of your switches. It says where it is up to on its own light, so you do not have to come back here to find out.</p>
          <ul class="bridge-lights">
            <li v-for="l in LIGHTS" :key="l.light" :class="{ good: l.light === 'green' }">
              <BridgeArt :light="l.light" />
              <span class="bridge-name">{{ l.name }}</span>
              <span class="bridge-sub">{{ l.sub }}</span>
            </li>
          </ul>
          <div class="bridge-row" :class="{ good: b.signal === 'strong' }">
            <span class="bridge-icon" :class="{ good: b.signal === 'strong' }"><Icon :name="b.signal === 'strong' ? 'check' : 'sparkle'" :size="18" /></span>
            <span class="bridge-text">
              <span class="bridge-name">{{ heard }}</span>
              <span class="bridge-sub" v-if="b.signal === 'strong'">Strong. Where it is now is good.</span>
              <span class="bridge-sub" v-else-if="b.signal === 'weak'">Faint. It will work, but a socket nearer a switch would be better.</span>
              <!-- Not "updates as you walk": unplugged, it has no Wi-Fi and cannot say anything at
                   all, so this only moves once it is on a charger somewhere. The light is what
                   answers while it is in your hand (design/puck/Placing.dc.html). -->
              <span class="bridge-sub" v-else-if="b.quiet">It has not come back. That socket may be out of Wi‑Fi reach — try one nearer the hub, or bring it back here.</span>
              <span class="bridge-sub" v-else>Plug it in and this will say what it hears.</span>
            </span>
          </div>
          <div class="flow-actions"><button class="button" :class="{ busy }" @click="placed">Leave it here</button></div>
        </template>

        <!-- it is somewhere, and a pile of switches came in with it -->
        <template v-else-if="b.state === 'ready'">
          <p class="flow-done">
            <span class="done-icon"><Icon name="check" :size="20" /></span>
            <span v-if="b.switches">{{ b.switches === 1 ? 'One switch came in with it' : `${b.switches} switches came in with it` }}. They work from the wall and the phone already.</span>
            <span v-else>It is on the house. Switches appear here as it hears them.</span>
          </p>
          <p class="sheet-lede" v-if="b.unplaced">What nobody knows yet is which is which. That is one walk around the house, pressing them.</p>
          <div class="flow-actions">
            <button class="button" v-if="b.unplaced" @click="close(); store.sheet = 'add'">Put them in rooms</button>
            <button class="button" :class="{ ghost: !!b.unplaced }" @click="close">Done</button>
          </div>
        </template>

        <!-- it needs the one thing the hub cannot know on its own -->
        <template v-else-if="b.needs === 'wifi'">
          <p class="sheet-lede">The hub is on a cable, so it has never needed the house's Wi‑Fi. The bridge does. Tell it once; nothing after this asks again.</p>
          <label class="field"><span class="field-label">Wi‑Fi name</span><input class="input" v-model="ssid" autocomplete="off" autocapitalize="off" spellcheck="false" @keydown.enter="tell" /></label>
          <label class="field"><span class="field-label">Password</span><input class="input" type="password" v-model="password" autocomplete="off" @keydown.enter="tell" /></label>
          <div class="flow-actions">
            <button class="button" :class="{ busy }" @click="tell">Use it</button>
            <button class="button ghost" @click="close">Not now</button>
          </div>
        </template>

        <!-- it did not work, in the brain's words -->
        <template v-else>
          <p class="sheet-lede">{{ b.text || 'The hub could not finish setting it up.' }}</p>
          <div class="flow-actions"><button class="button" @click="close">OK</button></div>
        </template>
      </div>
    </div>
  </div>
</template>
