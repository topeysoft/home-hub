<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { store, cap, houseLine, whatsOn, describe, ago, refreshEvents, loadHealth } from '../store'
import { type Room } from '../api'
import { upcomingLine } from '../upcoming'
import Icon from '../Icon.vue'
import SceneBar from '../SceneBar.vue'
import OnNow from '../OnNow.vue'
import Attention from '../Attention.vue'
import RoomGrid from '../RoomGrid.vue'
import CameraTile from '../tiles/CameraTile.vue'

const props = defineProps<{ rooms: Room[]; now: Date; topNav?: boolean }>()   // now: the clock the shell shows, so a preview hour agrees with itself; topNav: the command box is in the bar below
defineEmits<{ open: [id: string] }>()

const hour = computed(() => props.now.getHours())
const greeting = computed(() => hour.value < 5 ? 'Good night' : hour.value < 12 ? 'Good morning' : hour.value < 17 ? 'Good afternoon' : hour.value < 21 ? 'Good evening' : 'Good night')
const line = computed(houseLine)
const next = computed(() => upcomingLine(props.now))   // what the house will do next on its own
const anyOn = computed(() => whatsOn().length > 0)
const cameras = computed(() => props.rooms.flatMap(r => r.devices.filter(d => cap(d) === 'camera')))

const now = ref(Date.now())
const recent = computed(() => {
  const out: { key: number; text: string; icon: string; when: string }[] = []
  let last = ''
  for (const ev of store.events) {
    const d = describe(ev); if (!d || d.text === last) continue
    last = d.text; out.push({ key: ev.ts, text: d.text, icon: d.icon, when: ago(ev.ts, now.value) })
    if (out.length >= 4) break
  }
  return out
})
let t1: number | undefined, t2: number | undefined, t3: number | undefined
onMounted(() => { refreshEvents(); loadHealth(); t1 = window.setInterval(refreshEvents, 30000); t2 = window.setInterval(() => (now.value = Date.now()), 20000); t3 = window.setInterval(loadHealth, 60000) })
onUnmounted(() => { clearInterval(t1); clearInterval(t2); clearInterval(t3) })
</script>

<template>
  <section class="home">
    <header class="stage-head home-head">
      <div>
        <h1 class="display">{{ greeting }}</h1>
        <p class="lede">{{ line }}</p>
        <p class="home-next" v-if="next"><Icon name="sparkle" :size="14" />{{ next }}</p>
      </div>
      <SceneBar :room="null" />
    </header>

    <Attention :say="!topNav" />

    <div class="block" v-if="anyOn">
      <h2 class="label">On right now</h2>
      <OnNow />
    </div>

    <div class="block" v-if="cameras.length">
      <h2 class="label">Cameras</h2>
      <div class="camera-row">
        <CameraTile v-for="c in cameras" :key="c.id" :device="c" compact v-hold="() => (store.opened = c)" />
      </div>
    </div>
    <div class="block">
      <h2 class="label">Rooms</h2>
      <RoomGrid :rooms="rooms" @open="$emit('open', $event)" />
    </div>

    <div class="block" v-if="recent.length">
      <h2 class="label">Recently</h2>
      <ul class="recent">
        <li v-for="e in recent" :key="e.key">
          <span class="recent-icon"><Icon :name="e.icon" :size="16" /></span>
          <span class="recent-text">{{ e.text }}</span>
          <span class="recent-when">{{ e.when }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>
