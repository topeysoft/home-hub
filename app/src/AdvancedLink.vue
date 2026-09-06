<script setup lang="ts">
import { ref } from 'vue'
import { getAdvanced } from './api'
import { notify } from './store'

/* The Advanced door: Home Assistant's own UI, and its sign-in, which the hub made up and keeps behind the code. */
const props = defineProps<{ path?: string; text?: string }>()
const url = `${location.protocol}//${location.hostname}:8123${props.path ?? '/'}`
const login = ref<{ username: string | null; password: string | null } | null>(null), busy = ref(false)
async function reveal() {
  busy.value = true
  try { login.value = await getAdvanced() } catch (e: any) { notify(e.message, 'error') }
  busy.value = false
}
</script>

<template>
  <p class="sheet-foot">
    Advanced: <a :href="url" target="_blank" rel="noopener">open Home Assistant</a> {{ text ?? 'for the raw system behind this panel.' }}
    <template v-if="!login"> <button class="linkish" :disabled="busy" @click="reveal">Show its sign-in</button></template>
    <span class="advanced-login" v-else>Name <b>{{ login.username ?? '—' }}</b> · password <b>{{ login.password ?? '—' }}</b></span>
  </p>
</template>
