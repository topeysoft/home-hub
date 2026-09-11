<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { store } from './store'
import Icon from './Icon.vue'
import AdvancedLink from './AdvancedLink.vue'
import AddPanel from './AddPanel.vue'
import Drivers from './Drivers.vue'

/* Usually this sheet is for adding. It is also where a conversation the house already has open is
   picked up, so it takes that once on the way in and then reads as being about that one job. */
const resume = store.resume
store.resume = null

function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" :aria-label="resume ? 'Sign in again' : 'Add a device'">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">{{ resume ? 'Sign in again' : 'Add to the house' }}</h2>
      <p class="sheet-lede" v-if="resume">The house remembers everything else about this one. This is the part only you can do.</p>
      <p class="sheet-lede" v-else>Plug the new thing in and put it on the Wi‑Fi with its own app if it needs that. Then it turns up here.</p>
      <AddPanel :resume="resume" />
      <template v-if="!resume">
        <div class="add-block">
          <h3 class="label">Behind the scenes</h3>
          <Drivers />
        </div>
        <AdvancedLink path="/config/integrations" text="for anything this page cannot add." />
      </template>
    </div>
  </div>
</template>
