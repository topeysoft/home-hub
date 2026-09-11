<script setup lang="ts">
import AdvancedLink from './AdvancedLink.vue'
import AddPanel from './AddPanel.vue'
import Drivers from './Drivers.vue'

/* Usually this page is for adding. It is also where a conversation the house already has open is
   picked up; the panel takes that on the way in and hands it here, so the page reads as being about that one job. */
defineProps<{ resume: string | null }>()
</script>

<template>
  <div class="page">
    <p class="page-lede" v-if="resume">The house remembers everything else about this one. This is the part only you can do.</p>
    <p class="page-lede" v-else>Plug the new thing in and put it on the Wi‑Fi with its own app if it needs that. Then it turns up here.</p>
    <AddPanel :resume="resume" />
    <template v-if="!resume">
      <div class="add-block">
        <h3 class="label">Behind the scenes</h3>
        <Drivers />
      </div>
      <AdvancedLink path="/config/integrations" text="for anything this page cannot add." />
    </template>
  </div>
</template>
