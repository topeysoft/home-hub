<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { addRoom, placeScreen, type Phone, type Room } from './api'
import { keepScreenRoom, openOn, roomLine } from './screen'
import Icon from './Icon.vue'

/* Which room this screen is in (design/companion/, C). Asked once, after it has joined, never before:
   a device on the Wi-Fi without the passcode never sees the house's rooms. */
const props = defineProps<{ home: string; locked: boolean; rooms: Room[]; screens: Phone[] }>()
const emit = defineEmits<{ placed: [id: string] }>()
const picked = ref<string | null>(null), naming = ref(false), fresh = ref(''), busy = ref(false), error = ref('')
const choices = computed(() => props.rooms.filter(r => r.id !== 'unassigned'))
const chosen = computed(() => choices.value.find(r => r.id === picked.value) ?? null)

async function name() {
  const n = fresh.value.trim()
  if (!n || busy.value) return
  busy.value = true; error.value = ''
  try { const r = await addRoom(n); picked.value = r.id; naming.value = false; fresh.value = '' } catch (e: any) { error.value = e.message }
  busy.value = false
}
async function done() {
  if (!picked.value || busy.value) return
  busy.value = true; error.value = ''
  try { await placeScreen(picked.value); keepScreenRoom(picked.value); emit('placed', picked.value) } catch (e: any) { error.value = e.message }
  busy.value = false
}
</script>

<template>
  <main class="setup screen-room">
    <section class="setup-page">
      <p class="screen-trail">
        <span class="screen-trail-ok"><Icon name="check" :size="13" /></span><b>{{ home }}</b>
        <template v-if="locked"><span>·</span><span class="screen-trail-ok"><Icon name="check" :size="13" /></span><b>Passcode</b></template>
        <span>·</span><span class="screen-trail-now">Room</span>
      </p>
      <h1 class="display">Which room is this screen in?</h1>
      <p class="setup-lede">It opens on that room, and goes back to it after resting.</p>
      <div class="screen-rooms">
        <button v-for="r in choices" :key="r.id" class="screen-room-tile" :class="{ on: picked === r.id }" @click="picked = r.id">
          <span class="screen-room-name">{{ r.name }}</span><span class="screen-room-line">{{ roomLine(r, screens) }}</span>
        </button>
        <button v-if="!naming" class="screen-room-tile new" @click="naming = true">
          <span class="screen-room-name">Somewhere new</span><span class="screen-room-line">name a room</span>
        </button>
        <label v-else class="screen-room-tile new naming">
          <input class="screen-room-input" v-model="fresh" placeholder="Hallway" autocapitalize="words" aria-label="The room's name" @keydown.enter="name" />
          <button class="linkish" :disabled="!fresh.trim()" @click="name">Add</button>
        </label>
      </div>
      <p class="error" v-if="error">{{ error }}</p>
      <div class="setup-actions">
        <button class="button big" :class="{ busy }" :disabled="!chosen" @click="done">{{ chosen ? openOn(chosen.name) : 'Pick a room' }}</button>
      </div>
      <p class="setup-foot">You can change it later from this screen, under How it looks.</p>
    </section>
  </main>
</template>
