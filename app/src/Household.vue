<script setup lang="ts">
/*
 * The bar along the bottom, under the Top navigation: the command box on the
 * left, and the household on the right -- who the house knows, and who is in.
 * Real presence from the brain, not decoration: a person is drawn dim when they
 * are out. The household says nothing at all when the house has no people set
 * up, rather than drawing a strip of nobody; the box is always there, because
 * telling the house things is what Home is for (layout.ts).
 *
 * room: the room the panel is showing, so "lights off" said here means that
 * room, the same as the box inside a room would.
 */
import { computed } from 'vue'
import { store } from './store'
import Say from './Say.vue'

defineProps<{ room?: string | null }>()

const people = computed(() => store.presence?.people ?? [])
const initials = (n: string) => n.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('')
const line = computed(() => {
  const home = people.value.filter(p => p.home === true).map(p => p.name)
  if (!people.value.length) return ''
  if (!home.length) return 'Nobody home'
  if (home.length === people.value.length) return 'Everyone home'
  return home.length === 1 ? `${home[0]} is home` : `${home.slice(0, -1).join(', ')} and ${home[home.length - 1]} are home`
})
</script>

<template>
  <footer class="bottombar">
    <Say :room="room" />
    <div class="household" v-if="people.length" aria-label="Household">
      <span class="household-line">{{ line }}</span>
      <span class="household-label">Family</span>
      <div class="household-people">
        <span v-for="p in people" :key="p.name" class="person" :class="{ out: p.home === false, unknown: p.home === null }" :title="p.name">{{ initials(p.name) }}</span>
      </div>
    </div>
  </footer>
</template>
