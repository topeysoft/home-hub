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
import { store, notify } from './store'
import { removePhone, type Phone } from './api'
import { initials, personTone } from './people'
import Icon from './Icon.vue'
import PhoneSteps from './PhoneSteps.vue'

const people = computed(() => store.presence?.people ?? [])
const state = (home: boolean | null) => home === true ? 'Home' : home === false ? 'Away' : 'Not sure'

/* the phones that belong to the house: who, since when, for how long, and one way out each */
const HOW: Record<string, string> = { code: 'typed the code', wall: 'let in from the wall', setup: 'set up the house' }
const day = (ts: number) => new Date(ts * 1000).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
function phoneLine(p: Phone) {
  const bits = [`${HOW[p.how] ?? 'joined'} ${day(p.joined)}`]
  if (p.expires) bits.push(`until ${day(p.expires)}`)
  return bits.join(' · ')
}
const sure = ref(''), removing = ref('')
async function remove(p: Phone) {
  if (sure.value !== p.id) { sure.value = p.id; return }         // one tap asks, the second does
  removing.value = p.id
  try { await removePhone(p.id); notify(p.me ? 'This phone is out. Join again from the wall.' : `${p.name} is out.`) }
  catch (e: any) { if (e.message !== 'That needs the code.') notify(e.message, 'error') }
  sure.value = ''; removing.value = ''
}
const adding = ref(new URLSearchParams(location.search).get('add') === '1')   // ?sheet=people&add=1 previews the steps

</script>

<template>
  <div class="page">
    <p class="page-lede">Who the house knows, and the phones it lets in. A person is a phone: no accounts, no passwords.</p>

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
        <span class="hub-v">Nobody yet.<span class="hub-sub"> Once the house knows who lives here it can say who is in, and greet them by name.</span></span>
        <span></span>
      </li>
      <li>
        <span class="hub-k">Add</span>
        <span class="hub-v">Put the house on their phone. Scan once, and it opens like an app from their first screen.</span>
        <button class="button small" @click="adding = !adding">{{ adding ? 'Hide' : 'Show how' }}</button>
      </li>
      <li class="hub-wide" v-if="adding"><PhoneSteps /></li>
      <li v-if="store.status?.locked">
        <span class="hub-k">Phones</span>
        <span class="hub-v">{{ store.phones.length === 1 ? 'One phone belongs' : `${store.phones.length} phones belong` }} to the house. Each runs it from the Wi‑Fi; none reaches it from outside yet.<span class="hub-sub"> A phone that is removed is out at once.</span></span>
        <span></span>
      </li>
      <li class="hub-wide" v-if="store.status?.locked && store.phones.length">
        <ul class="phones">
          <li v-for="p in store.phones" :key="p.id">
            <span class="phones-icon"><Icon :name="p.kind === 'wall' ? 'home' : 'phone'" :size="16" /></span>
            <span class="phones-text"><span class="phones-name">{{ p.name }}<span class="phones-me" v-if="p.me"> · this one</span></span><span class="phones-sub">{{ phoneLine(p) }}</span></span>
            <button class="button small ghost" :class="{ busy: removing === p.id, warn: sure === p.id }" @click="remove(p)">{{ sure === p.id ? (p.me ? 'Remove this one?' : 'Sure?') : 'Remove' }}</button>
          </li>
        </ul>
      </li>
      <li v-else-if="store.status?.setup_done && !store.status?.locked">
        <span class="hub-k">Phones</span>
        <span class="hub-v">Without a code, every phone on the Wi‑Fi can run the house.<span class="hub-sub"> Set one and only the phones you let in can.</span></span>
        <button class="button small" @click="store.sheet = 'code'">Set a code</button>
      </li>
    </ul>
  </div>
</template>
