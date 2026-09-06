<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { store } from './store'
import Icon from './Icon.vue'
import LocationPicker from './LocationPicker.vue'

function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
const advanced = `${location.protocol}//${location.hostname}:8123/`   // Home Assistant's own UI, for anyone who wants the raw system
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="Home location">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">Where is home?</h2>
      <p class="sheet-lede">The sky, sunrise and weather follow this. It stays on the hub and is never shared.</p>
      <LocationPicker @saved="close" />
      <p class="sheet-foot">Advanced: <a :href="advanced" target="_blank" rel="noopener">open Home Assistant</a> for the raw system behind this panel.</p>
    </div>
  </div>
</template>
