<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, notify, loadRoutines, visibleRooms } from './store'
import { enableRoutine, type Routine } from './api'
import { routineWords } from './why'
import Icon from './Icon.vue'

/* The routines sheet: every rule by room, each with its name and a switch. On or off is all the panel does; authoring is the assistant's job. */
const busy = ref('')
const groups = computed(() => {
  const order = ['home', ...visibleRooms().map(r => r.id)]
  const by = new Map<string, Routine[]>()
  for (const r of store.routines) by.set(r.room, [...(by.get(r.room) ?? []), r])
  const rank = (id: string) => { const i = order.indexOf(id); return i < 0 ? 999 : i }
  return [...by.keys()].sort((a, b) => rank(a) - rank(b))
    .map(id => ({ id, name: id === 'home' ? 'Whole house' : store.rooms.find(r => r.id === id)?.name ?? id, rules: by.get(id)! }))
})
const on = (r: Routine) => r.enabled !== false

async function flip(r: Routine) {
  if (busy.value) return
  const want = !on(r)
  busy.value = r.id; r.enabled = want
  try { await enableRoutine(r.id, want) } catch (e: any) { r.enabled = !want; notify(`That didn't stick: ${e.message}`, 'error') }
  busy.value = ''
}
function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => { window.addEventListener('keydown', key); loadRoutines() })
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="Routines">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">Routines</h2>
      <p class="sheet-lede">Small things the house does on its own. Switch one off and it stops until you switch it back. A scene you pick by hand always wins for a while.</p>
      <template v-for="g in groups" :key="g.id">
        <h3 class="label routines-head">{{ g.name }}</h3>
        <ul class="routines">
          <li v-for="r in g.rules" :key="r.id" :class="{ off: !on(r) }">
            <span class="routine-text"><span class="routine-name">{{ r.name }}</span><span class="routine-sub">{{ routineWords(r) }}</span></span>
            <button class="switch" role="switch" :aria-checked="on(r)" :aria-label="`${r.name}: ${on(r) ? 'on' : 'off'}`" :class="{ on: on(r), busy: busy === r.id }" @click="flip(r)"><span class="knob"></span></button>
          </li>
        </ul>
      </template>
      <p class="sheet-status" v-if="!store.routines.length && !store.routineErrors.length">No routines yet. The house only does what you tell it.</p>
      <div class="add-block" v-if="store.routineErrors.length">
        <h3 class="label routines-head">Couldn't be read</h3>
        <p class="sheet-status">Some routines on the hub have a mistake in them and are skipped until it is fixed:</p>
        <ul class="routine-errors"><li v-for="e in store.routineErrors" :key="e">{{ e }}</li></ul>
      </div>
      <p class="sheet-foot">For now, new routines are added on the hub itself. Asking for one in plain words is coming.</p>
    </div>
  </div>
</template>
