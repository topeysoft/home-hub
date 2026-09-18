<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * Accounts: every service the house has signed into, and the two things a person
 * can do about one — finish a sign-in it is waiting on, or be done with it.
 *
 * There is no list of names here deciding what an account is. The brain answers
 * with whatever brought something into the house or wants something from a
 * person, which keeps the weather and the clock off a page about accounts, and
 * keeps the driver layer's plumbing off it too: the brain set that up itself and
 * nobody ever signed into it (docs/settings.md, Accounts).
 *
 * Removing one is the end of everything it brought, so the row says how much
 * that is before it asks, and asks twice.
 */
import { computed, ref } from 'vue'
import { store, notify } from './store'
import { loadAccounts } from './store'
import { removeAccount, type Account } from './api'
import Icon from './Icon.vue'

const accounts = computed(() => store.accounts)
const WORD: Record<Account['state'], string> = { on: 'Signed in', signin: 'Needs signing in', stopped: 'Not answering' }
const ICON: Record<Account['state'], string> = { on: 'check', signin: 'lock', stopped: 'bolt' }
/* the maker's name for the thing, but only when it says something the house's own name for it does not */
const kindOf = (a: Account) => a.kind && !a.name.toLowerCase().includes(a.kind.toLowerCase()) ? a.kind : ''

/* what disappears with it, in things rather than in the engine's words */
function brought(a: Account) {
  if (!a.things) return 'Nothing of the house came in with it'
  return a.things === 1 ? '1 thing in the house came in with it' : `${a.things} things in the house came in with it`
}
/* Every row says the same two things in the same order: how it stands, then how much of the house is
   behind it. A sign-in used to explain itself here as well, which on a phone squeezed the text into a
   ribbon beside its own buttons -- and the button next to it already says what to do about it. */
function line(a: Account) {
  return a.state === 'stopped' && a.why ? a.why : brought(a)
}

/* finishing a sign-in is the conversation the Add page already draws; it is handed the flow and reads
   as being about that one job (docs/settings.md, What landed) */
function signIn(a: Account) { store.resume = a.flow; store.sheet = 'add' }

const sure = ref(''), busy = ref('')
async function remove(a: Account) {
  if (sure.value !== a.id) { sure.value = a.id; return }     // one tap asks with what goes, the second does
  busy.value = a.id
  try { await removeAccount(a.id); notify(`${a.name} is out. ${a.things ? 'What it brought goes with it.' : ''}`.trim()); await loadAccounts() }
  catch (e: any) { if (e.message !== 'That needs the code.') notify(e.message, 'error') }
  sure.value = ''; busy.value = ''
}
</script>

<template>
  <div class="page">
    <p class="page-lede">Everything the house has signed into. Removing one takes back everything it brought, so the house asks first.</p>

    <ul class="hub-rows">
      <li class="hub-wide" v-if="accounts.length">
        <ul class="phones">
          <li v-for="a in accounts" :key="a.id">
            <span class="phones-icon"><Icon :name="ICON[a.state]" :size="16" /></span>
            <span class="phones-text">
              <span class="phones-name">{{ a.name }}<span class="phones-me" v-if="kindOf(a)"> · {{ kindOf(a) }}</span></span>
              <span class="phones-sub">{{ WORD[a.state] }} · {{ line(a) }}</span>
            </span>
            <!-- one cell, so a row with two things to offer stays a row: .phones li is a three-column grid -->
            <span class="phones-do">
              <button class="button small" v-if="a.state === 'signin' && a.flow" @click="signIn(a)">Sign in again</button>
              <button class="button small ghost" :class="{ busy: busy === a.id, warn: sure === a.id }" @click="remove(a)">
                {{ sure === a.id ? (a.things ? `Remove, and the ${a.things} things?` : 'Remove it?') : 'Remove' }}
              </button>
            </span>
          </li>
        </ul>
      </li>
      <li v-else>
        <span class="hub-k">Accounts</span>
        <span class="hub-v">Nothing signed in yet.<span class="hub-sub line">Things that live behind an account — a camera, a thermostat, a doorbell — are added from <i>Add a device</i>, and appear here once they are.</span></span>
        <button class="button small" @click="store.sheet = 'add'">Add a device</button>
      </li>
    </ul>
  </div>
</template>
