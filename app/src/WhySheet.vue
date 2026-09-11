<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { store, notify } from './store'
import { getWhy, explainRoom, type Event } from './api'
import { explain, whenText } from './why'
import Icon from './Icon.vue'

/* Why a room is the way it is: its last few intent events from the log, each as a sentence. Rendered, never generated. */
const room = computed(() => store.rooms.find(r => r.id === store.whyRoom) ?? null)
const events = ref<Event[]>([]), loading = ref(true), now = ref(Date.now())
const rows = computed(() => events.value.map(ev => ({ key: `${ev.ts}-${ev.kind}`, ...explain(ev), when: whenText(ev.ts, now.value) })))

function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
async function look() {
  if (!store.whyRoom) { loading.value = false; return }
  try { events.value = await getWhy(store.whyRoom); now.value = Date.now() } catch (e: any) { notify(e.message, 'error') }
  loading.value = false
}
watch(() => store.events, look)   // a fresh event just landed: the list should already know

/* a question in plain words, answered from the same log by the assistant */
const question = ref(''), asking = ref(false), answer = ref('')
async function ask() {
  if (!store.whyRoom || asking.value) return
  asking.value = true
  try { answer.value = (await explainRoom(store.whyRoom, question.value.trim())).answer }
  catch (e: any) { notify(e.message, 'error') }
  asking.value = false
}
onMounted(() => { window.addEventListener('keydown', key); look() })
onUnmounted(() => window.removeEventListener('keydown', key))
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="Why this room is like this">
      <div class="sheet-head">
        <h2 class="display">Why the {{ room?.name ?? 'room' }} is like this</h2>
        <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      </div>
      <div class="sheet-body">
      <p class="sheet-lede">The last few times this room changed, and what changed it.</p>
      <p class="sheet-status" v-if="loading">Looking back…</p>
      <p class="sheet-status" v-else-if="!rows.length">Nothing has set this room yet. Pick a scene, or wait for a routine to notice something.</p>
      <ul class="why" v-else>
        <li v-for="r in rows" :key="r.key">
          <span class="why-icon"><Icon :name="r.icon" :size="16" /></span>
          <span class="why-text"><span class="why-main">{{ r.text }}</span><span class="why-sub">{{ r.sub }}</span></span>
          <span class="why-when">{{ r.when }}</span>
        </li>
      </ul>
      <form class="search ask-why" v-if="store.assistant?.configured" @submit.prevent="ask">
        <Icon name="sparkle" :size="18" />
        <input v-model="question" :disabled="asking" placeholder="Ask, like “why did the light come on?”" aria-label="Ask about this room" />
        <button class="button small" type="submit" :class="{ busy: asking }">{{ asking ? 'Thinking…' : 'Ask' }}</button>
      </form>
      <p class="why-answer" v-if="answer">{{ answer }}</p>
      <p class="sheet-foot" v-if="store.routines.length || store.assistant?.configured">Routines decide these on their own. <button class="linkish" @click="store.sheet = 'routines'">See them all</button></p>
      </div>
    </div>
  </div>
</template>
