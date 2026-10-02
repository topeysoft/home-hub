<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * People and phones. Who the house knows and who is in, as the house sees it;
 * the phones that belong to it, with one way out each; and how one more person
 * joins. A person is a phone, not an account: the house goes onto their phone
 * and that phone is theirs from then on (docs/settings.md, People).
 *
 * The phones used to live on the hub page. They are about who, not about the
 * little computer, so they moved here with the people they belong to.
 */
import { computed, ref } from 'vue'
import { store, notify, holdsKeys, loadPhones } from './store'
import { letOut, removePhone, type Phone } from './api'
import { switchFor } from './move'
import { seen } from './seen'
import { initials, personTone } from './people'
import Icon from './Icon.vue'
import PhoneSteps from './PhoneSteps.vue'
import { locale } from './lang'

const people = computed(() => store.presence?.people ?? [])
const state = (home: boolean | null) => home === true ? 'Home' : home === false ? 'Away' : 'Not sure'

/* the phones that belong to the house: who, since when, for how long, and one way out each */
const HOW: Record<string, string> = { code: 'joined with the passcode', wall: 'allowed from the wall screen', setup: 'set up the house' }
/* the wall was named "This wall" when the house was set up; to anyone else it is the screen on the wall */
const phoneName = (p: Phone) => p.kind === 'wall' && p.name === 'This wall' ? 'Wall screen' : p.name
const day = (ts: number) => new Date(ts * 1000).toLocaleDateString(locale(), { weekday: 'short', month: 'short', day: 'numeric' })
function phoneLine(p: Phone) {
  const bits = [`${HOW[p.how] ?? 'joined'} ${day(p.joined)}`, seen(p.last_seen)]   // seen: what tells five rows of the same name apart
  if (p.expires) bits.push(`until ${day(p.expires)}`)
  return bits.join(' · ')
}
const sure = ref(''), removing = ref('')
async function remove(p: Phone) {
  if (sure.value !== p.id) { sure.value = p.id; return }         // one tap asks, the second does
  removing.value = p.id
  try { await removePhone(p.id); notify(p.me ? 'This phone is removed. To use the house again, join from the wall screen.' : `${phoneName(p)} is removed.`) }
  catch (e: any) { if (e.message !== 'That needs the passcode.') notify(e.message, 'error') }
  sure.value = ''; removing.value = ''
}
const adding = ref(new URLSearchParams(location.search).get('add') === '1')

/* Home only, or Anywhere (design/words-people/, C; the switch itself is design/away/, C): per phone, Home only
   for all of them until somebody who keeps the house picks Anywhere for one. Only once the house has an
   address -- before that there is nowhere else to reach it from -- and never for the wall, which stays home.
   The choice used to be a switch labeled From outside, which nobody new could read (docs/wording.md). */
const outside = (p: Phone) => switchFor(p, !!store.me?.address, keys.value)
const address = computed(() => (store.me?.address ?? '').replace(/^https:\/\//, ''))
const letting = ref('')
async function pick(p: Phone, anywhere: boolean) {
  if (anywhere === p.remote || letting.value) return
  letting.value = p.id
  try { await letOut(p.id, anywhere); await loadPhones(true); notify(anywhere ? `${p.name} works anywhere now.` : `${p.name} works at home only now.`) }
  catch (e: any) { notify(e.message, 'error') }
  letting.value = ''
}   // ?sheet=people&add=1 previews the steps

/* A phone that was let in at a wall is shown itself and nobody else -- the hub answers /phones with what
   this phone may see, not with the household. So the count below would be reading its own row back as
   "One phone can use the house", which is both wrong and the kind of wrong that reads as a bug. It
   says what is true instead: this is your phone, here is the way out of the house, and the rest of it is
   not yours to see. */
const keys = computed(() => holdsKeys())

</script>

<template>
  <div class="page">
    <p class="page-lede">Who lives here, and the phones that can use the house. No accounts or passwords: each person’s phone is their way in.</p>

    <ul class="hub-rows">
      <li class="hub-wide" v-if="people.length">
        <ul class="phones">
          <li v-for="(p, i) in people" :key="p.name" class="people-row">
            <span class="person" :class="{ out: p.home === false, unknown: p.home === null }" :style="{ background: personTone(i) }">{{ initials(p.name) }}</span>
            <span class="phones-text"><span class="phones-name">{{ p.name }}</span></span>
            <span class="people-state" :class="{ in: p.home === true }">{{ state(p.home) }}</span>
          </li>
        </ul>
      </li>
      <li v-else>
        <span class="hub-k">Household</span>
        <span class="hub-v">Nobody yet.<span class="hub-sub line">Once the house knows who lives here it can say who is in, and greet them by name.</span></span>
        <span></span>
      </li>
      <li>
        <span class="hub-k">Add</span>
        <span class="hub-v">Add someone’s phone.<span class="hub-sub line">They scan the code once, and the house opens like an app from their home screen.</span></span>
        <button class="button small" @click="adding = !adding">{{ adding ? 'Hide' : 'Show how' }}</button>
      </li>
      <li class="hub-wide" v-if="adding"><PhoneSteps /></li>
      <li v-if="store.status?.locked && keys">
        <span class="hub-k">Phones</span>
        <span class="hub-v">{{ store.phones.length === 1 ? 'One phone can' : `${store.phones.length} phones can` }} use the house.<span class="hub-sub line">Each works at home, on your Wi‑Fi.<template v-if="address"> Set one to Anywhere and it works wherever you are, at <b>{{ address }}</b>.</template> Removing a phone locks it out straight away.</span></span>
        <span></span>
      </li>
      <li v-else-if="store.status?.locked">
        <span class="hub-k">This phone</span>
        <span class="hub-v">This phone was allowed in from the wall screen, so it can use the house but not change who else can.<span class="hub-sub line">Adding or removing other phones takes the passcode. You can remove this one below whenever you like.</span></span>
        <span></span>
      </li>
      <li class="hub-wide" v-if="store.status?.locked && store.phones.length">
        <ul class="phones">
          <li v-for="p in store.phones" :key="p.id">
            <span class="phones-icon"><Icon :name="p.kind === 'wall' ? 'home' : 'phone'" :size="16" /></span>
            <span class="phones-text"><span class="phones-name">{{ phoneName(p) }}<span class="phones-me" v-if="p.me"> · this one</span></span><span class="phones-sub">{{ phoneLine(p) }}</span></span>
            <span class="phones-where" v-if="address && keys && p.kind === 'wall'"><span class="where-fixed">Home only</span></span>
            <span class="phones-where" v-else-if="outside(p)"><span class="where-pick" :class="{ busy: letting === p.id }" role="radiogroup" :aria-label="`Where ${phoneName(p)} works`"><button role="radio" :aria-checked="!p.remote" @click="pick(p, false)">Home only</button><button role="radio" :aria-checked="p.remote" @click="pick(p, true)">Anywhere</button></span></span>
            <button class="button small ghost" :class="{ busy: removing === p.id, warn: sure === p.id }" @click="remove(p)">{{ sure === p.id ? (p.me ? 'Remove this one?' : 'Sure?') : 'Remove' }}</button>
          </li>
        </ul>
      </li>
      <li v-else-if="store.status?.setup_done && !store.status?.locked">
        <span class="hub-k">Phones</span>
        <span class="hub-v">Without a passcode, any phone on your Wi‑Fi can use the house.<span class="hub-sub line">Set one, and only the phones you add can.</span></span>
        <button class="button small" @click="store.sheet = 'code'">Set a passcode</button>
      </li>
    </ul>
  </div>
</template>
