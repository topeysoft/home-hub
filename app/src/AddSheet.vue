<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { store } from './store'
import Icon from './Icon.vue'
import AddPanel from './AddPanel.vue'

function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
const advanced = `${location.protocol}//${location.hostname}:8123/config/integrations`
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="Add a device">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">Add to the house</h2>
      <p class="sheet-lede">Plug the new thing in and put it on the Wi‑Fi with its own app if it needs that. Then it turns up here.</p>
      <AddPanel />
      <p class="sheet-foot">Advanced: <a :href="advanced" target="_blank" rel="noopener">open Home Assistant</a> for anything this page cannot add.</p>
    </div>
  </div>
</template>
