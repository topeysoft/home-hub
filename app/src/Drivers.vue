<script setup lang="ts">
import { computed } from 'vue'
import { store } from './store'

/* What is running behind the panel, in plain words: the radios, Matter, Ring. The brain connects
   each one to the engine itself; the only thing a person ever does here is sign in to Ring. */
const parts = computed(() => store.status?.drivers ?? [])
const attention = computed(() => parts.value.some(p => p.state === 'sign-in' || p.state === 'failed'))
const link = (port: number) => `${location.protocol}//${location.hostname}:${port}`
defineExpose({ attention })
</script>

<template>
  <ul class="drivers" v-if="parts.length">
    <li v-for="p in parts" :key="p.id" :class="p.state">
      <span class="drv-dot"></span>
      <span class="drv-text"><span class="drv-name">{{ p.name }}</span><span class="drv-sub">{{ p.text }}</span></span>
      <a v-if="p.state === 'sign-in'" class="button small" :href="link(p.port)" target="_blank" rel="noopener">Sign in</a>
    </li>
  </ul>
</template>
