<script setup lang="ts">
/*
 * The bar along the bottom, under the Top navigation: the command box on the
 * left, and the household on the right -- who the house knows, and who is in.
 * Real presence from the brain, not decoration: a person keeps their colour and
 * their initial but goes quiet when they are out. The last circle is always the + that adds
 * one more, as drawn, so a house with nobody set up still shows where people
 * go. The box is always there, because telling the house things is what Home
 * is for (layout.ts).
 *
 * room: the room the panel is showing, so "lights off" said here means that
 * room, the same as the box inside a room would.
 */
import { computed } from 'vue'
import { store } from './store'
import { initials, personTone } from './people'
import Icon from './Icon.vue'
import Say from './Say.vue'

defineProps<{ room?: string | null }>()

const people = computed(() => store.presence?.people ?? [])
const line = computed(() => {
  const home = people.value.filter(p => p.home === true).map(p => p.name)
  if (!people.value.length) return ''
  if (!home.length) return 'Nobody home'
  if (home.length === people.value.length) return 'Everyone home'
  return home.length === 1 ? `${home[0]} is home` : `${home.slice(0, -1).join(', ')} and ${home[home.length - 1]} are home`
})
const open = () => (store.sheet = 'people')
</script>

<template>
  <footer class="bottombar">
    <Say :room="room" />
    <div class="household" aria-label="Household">
      <span class="household-line" v-if="line">{{ line }}</span>
      <span class="household-label">Family</span>
      <div class="household-people">
        <button v-for="(p, i) in people" :key="p.name" class="person" :class="{ out: p.home === false, unknown: p.home === null }" :style="{ background: personTone(i) }"
                :title="`${p.name}, ${p.home === true ? 'home' : p.home === false ? 'away' : 'not sure'}`"
                :aria-label="`${p.name}, ${p.home === true ? 'home' : p.home === false ? 'away' : 'not sure'}`" @click="open">{{ initials(p.name) }}</button>
        <button class="person add" @click="open" aria-label="Add a person"><Icon name="plus" :size="14" /></button>
      </div>
    </div>
  </footer>
</template>
