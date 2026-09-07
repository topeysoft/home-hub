<script setup lang="ts">
import { ref } from 'vue'
import { restoreBackup } from './api'
import { store, notify } from './store'

/* Put a backup back: pick the file, the hub stops, unpacks and comes back as the house it was. */
const busy = ref(false), note = ref('')
async function pick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f || busy.value) return
  busy.value = true; note.value = ''
  try {
    const r = await restoreBackup(f)
    store.restoring = true
    note.value = `Restoring ${r.manifest?.home ? `“${r.manifest.home}”` : 'the backup'}. The hub restarts; this screen comes back on its own.`
  } catch (err: any) { note.value = err.message; notify(err.message, 'error') }
  busy.value = false
}
</script>

<template>
  <div class="restore">
    <label class="button ghost" :class="{ busy }">
      {{ busy ? 'Sending…' : 'Restore a backup' }}
      <input type="file" accept=".gz,.tgz,application/gzip,application/x-gzip" hidden :disabled="busy || store.restoring" @change="pick" />
    </label>
    <p class="field-hint" v-if="note">{{ note }}</p>
  </div>
</template>
