<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { lock, remember } from './code'
import Icon from './Icon.vue'

/* "What's the code?" Shown the moment something needs it; the request that asked carries on. */
const code = ref(''), input = ref<HTMLInputElement | null>(null)
function done(ok: boolean) {
  const p = lock.prompt; if (!p) return
  if (ok) remember(code.value.trim())
  lock.prompt = null; p.resolve(ok)
}
function submit() { if (code.value.trim().length >= 4) done(true) }
onMounted(() => nextTick(() => input.value?.focus()))
watch(() => lock.prompt, p => { if (p) { code.value = ''; nextTick(() => input.value?.focus()) } })
</script>

<template>
  <div class="sheet-back code-back" @click.self="done(false)">
    <div class="sheet code" role="dialog" aria-label="The code">
      <button class="round sheet-close" @click="done(false)" aria-label="Cancel"><Icon name="close" :size="20" /></button>
      <h2 class="display">What's the code?</h2>
      <p class="sheet-lede">{{ lock.prompt?.wrong ? "That wasn't it. Try again." : 'Changing the house needs the code that was set for it.' }}</p>
      <input ref="input" class="input code-input" v-model="code" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" maxlength="8" placeholder="••••" @keydown.enter="submit" />
      <div class="flow-actions">
        <button class="button" :disabled="code.trim().length < 4" @click="submit">Continue</button>
        <button class="button ghost" @click="done(false)">Cancel</button>
      </div>
    </div>
  </div>
</template>
