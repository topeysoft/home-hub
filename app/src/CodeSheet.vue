<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { setPin } from './api'
import { store, notify } from './store'
import { remember } from './code'
import Icon from './Icon.vue'
import AdvancedLink from './AdvancedLink.vue'

/* Set, change or remove the code on the settings. Changing one asks for the old one first, like any setting. */
const pin = ref(''), again = ref(''), busy = ref(false), error = ref('')
const has = () => !!store.status?.locked
function close() { store.sheet = null }
async function save(clear = false) {
  error.value = ''
  if (!clear) {
    if (!/^\d{4,8}$/.test(pin.value)) { error.value = 'A code is 4 to 8 digits.'; return }
    if (pin.value !== again.value) { error.value = 'The two do not match.'; return }
  }
  busy.value = true
  try {
    store.status = await setPin(clear ? '' : pin.value)
    remember(clear ? '' : pin.value)
    notify(clear ? 'The code is off. Anyone here can change the house.' : 'The settings are locked.')
    close()
  } catch (e: any) { error.value = e.message }
  busy.value = false
}
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="The code">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">{{ has() ? 'Change the code' : 'Lock the settings' }}</h2>
      <p class="sheet-lede">Lights, scenes and doors never need it. Adding devices, renaming, moving rooms and the Advanced door do. Pick 4 to 8 digits.</p>
      <label class="field"><span class="field-label">Code</span><input class="input code-input" v-model="pin" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="save()" /></label>
      <label class="field"><span class="field-label">Once more</span><input class="input code-input" v-model="again" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" @keydown.enter="save()" /></label>
      <p class="error" v-if="error">{{ error }}</p>
      <div class="flow-actions">
        <button class="button" :class="{ busy }" @click="save()">{{ has() ? 'Change it' : 'Lock' }}</button>
        <button class="button ghost" v-if="has()" :class="{ busy }" @click="save(true)">Remove the code</button>
      </div>
      <AdvancedLink />
    </div>
  </div>
</template>
