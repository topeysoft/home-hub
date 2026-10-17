<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { ref } from 'vue'
import { setPin } from './api'
import { store, notify } from './store'
import { remember } from './code'
import AdvancedLink from './AdvancedLink.vue'

/* Set, change or remove the code on the settings. Changing one asks for the old one first, like any setting. */
const pin = ref(''), again = ref(''), busy = ref(false), error = ref('')
const has = () => !!store.status?.locked
function close() { store.sheet = null }
async function save(clear = false) {
  error.value = ''
  if (!clear) {
    if (!/^\d{4,8}$/.test(pin.value)) { error.value = 'A passcode is 4 to 8 digits.'; return }
    if (pin.value !== again.value) { error.value = 'The two do not match.'; return }
  }
  busy.value = true
  try {
    store.status = await setPin(clear ? '' : pin.value)
    remember(clear ? '' : pin.value)
    notify(clear ? 'The passcode is removed. Anyone on your Wi‑Fi can change the house.' : 'The passcode is set.')
    close()
  } catch (e: any) { error.value = e.message }
  busy.value = false
}
</script>

<template>
  <div class="page">
    <p class="page-lede">Lights, scenes and locks never need it. Adding phones and devices, renaming, moving rooms and Advanced do. Pick 4 to 8 digits.</p>
    <label class="field"><span class="field-label">Passcode</span><input class="input code-input secret" v-model="pin" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="save()" /></label>
    <label class="field"><span class="field-label">Type it again</span><input class="input code-input secret" v-model="again" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="save()" /></label>
    <p class="error" v-if="error">{{ error }}</p>
    <div class="flow-actions">
      <button class="button" :class="{ busy }" @click="save()">{{ has() ? 'Change it' : 'Set a passcode' }}</button>
      <button class="button ghost" v-if="has()" :class="{ busy }" @click="save(true)">Remove the passcode</button>
    </div>
    <AdvancedLink />
  </div>
</template>
