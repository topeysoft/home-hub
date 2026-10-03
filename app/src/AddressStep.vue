<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * From outside, too? The last step of setup, and the only optional one (design/address/, C, worded
 * Plain). The house is complete without it; this is the one place it is offered, because a house that
 * has its address before the first phone joins never has to move a phone to it later.
 *
 * Three moments on one page. Asking: the address, filled in from what the house was just called, checked
 * as it is typed, with the price in the open and what stopping does. Then, once it is taken, either
 * the wall shows a code and a phone pays -- never the wall, which is shared and no place to type a card --
 * or, on the maker's own hub before payments exist, the house simply waits to be turned on. Either way
 * the step moves on by itself, and Not now is the same size as the button beside it at every moment.
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { claimAddress, getAddress, lookAddress, qrUrl, type AddressState, type NameLook } from './api'
import { cleanName, payUrl, price, takeWords, verdict, ZONE } from './address'
import Icon from './Icon.vue'

const props = defineProps<{ state: AddressState }>()
const emit = defineEmits<{ done: [] }>()

const typed = ref(props.state.guess)
const look = ref<NameLook | null>(null)
const suggestions = ref<string[]>([])
const moment = ref<'ask' | 'phone' | 'waiting'>('ask')
const house = ref('')
const busy = ref(false), error = ref('')
const said = computed(() => verdict(look.value, typed.value))
const cost = computed(() => price(props.state.offer))
const free = computed(() => said.value.tone === 'ok')
const pay = computed(() => payUrl(props.state.offer, house.value))

let timer: number | undefined
watch(typed, t => {
  clearTimeout(timer)
  const name = cleanName(t)
  if (!name) { look.value = null; suggestions.value = []; return }
  timer = window.setTimeout(async () => {
    try {
      const l = await lookAddress(name)
      if (cleanName(typed.value) !== name) return       // they kept typing; this answer is for a name nobody wants now
      look.value = l; suggestions.value = l.free ? [] : (l.suggestions ?? [])
    } catch (e: any) { error.value = e.message }
  }, 350)
}, { immediate: true })

let poll: number | undefined
async function take() {
  if (!free.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const a = await claimAddress(cleanName(typed.value))
    house.value = a.house ?? ''
    moment.value = props.state.offer.pay ? 'phone' : 'waiting'
    poll = window.setInterval(async () => {
      try { if ((await getAddress()).carried) { clearInterval(poll); emit('done') } } catch {}
    }, 3000)
  } catch (e: any) {
    if (e.suggestions) { look.value = { name: cleanName(typed.value), free: false, why: 'taken', suggestions: e.suggestions }; suggestions.value = e.suggestions }
    else error.value = e.message
  }
  busy.value = false
}
function pick(s: string) { typed.value = s }
onUnmounted(() => { clearTimeout(timer); clearInterval(poll) })
</script>

<template>
  <section class="setup-page address-step" v-if="moment === 'ask'">
    <p class="setup-step">Optional</p>
    <h1 class="display">Use it anywhere?</h1>
    <p class="setup-lede">The house already works fully at home. To use it on your phones when you are out, we connect it for you, through a service we run.</p>
    <div class="address-form">
      <span class="field-label">The house&rsquo;s web address</span>
      <div class="address-row">
        <label class="address-name">
          <input class="input" v-model="typed" autocapitalize="none" autocorrect="off" spellcheck="false" maxlength="40" aria-label="The house's web address" @keydown.enter="take" />
          <span class="address-zone">.{{ ZONE }}</span>
        </label>
        <span class="address-said" :class="said.tone" role="status"><Icon v-if="said.tone === 'ok'" name="check" :size="16" />{{ said.text }}</span>
      </div>
      <div class="address-picks" v-if="suggestions.length">
        <button v-for="s in suggestions" :key="s" class="chip-btn" @click="pick(s)"><b>{{ s }}</b><span>.{{ ZONE }}</span></button>
      </div>
      <p class="address-cost" v-if="cost"><span class="address-amount display">{{ cost.amount }}</span> {{ cost.rest }} &middot; stop any time</p>
      <p class="address-cost" v-else>Free for now. We turn it on for you.</p>
      <p class="address-stop">If you stop, phones go back to Home only. Everything at home carries on as it is, and we keep the web address for you for 60 days.</p>
      <p class="error" v-if="error">{{ error }}</p>
      <div class="setup-actions">
        <button class="button big" :class="{ busy }" :disabled="!free" @click="take">{{ takeWords(state.offer) }}</button>
        <button class="button ghost" @click="emit('done')">Not now</button>
      </div>
    </div>
    <p class="setup-foot">Have a server of your own? <a href="https://github.com/topeysoft/home-hub/blob/main/relay/README.md" target="_blank" rel="noopener">Use it instead</a>, free.</p>
  </section>

  <section class="setup-page address-step" v-else-if="moment === 'phone'">
    <p class="setup-step">Optional</p>
    <h1 class="display">Finish on your phone.</h1>
    <p class="setup-lede">Point your phone&rsquo;s camera here. It opens a payment page for <b>{{ house }}.{{ ZONE }}</b>; this screen moves on by itself when it is done.</p>
    <div class="address-pay">
      <div class="phone-qr" v-if="pay"><img :src="qrUrl(pay)" alt="A code the phone's camera opens the payment page from" width="132" height="132" /></div>
      <div class="address-wait">
        <p class="setup-status"><span class="pulse-dot"></span> Waiting for your phone&hellip;</p>
        <button class="button ghost" @click="emit('done')">Not now</button>
      </div>
    </div>
  </section>

  <section class="setup-page address-step" v-else>
    <p class="setup-step">Optional</p>
    <h1 class="display">Nearly there.</h1>
    <p class="setup-lede"><b>{{ house }}.{{ ZONE }}</b> is this house&rsquo;s now. We are turning it on; this screen moves on by itself when it is done.</p>
    <p class="setup-status"><span class="pulse-dot"></span> Turning it on&hellip;</p>
    <div class="setup-actions"><button class="button ghost" @click="emit('done')">Not now</button></div>
  </section>
</template>
