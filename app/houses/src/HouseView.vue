<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * One house: its own panel, framed from its own name -- at home its name on the Wi-Fi, out of the house its
 * name on the internet -- and handed this phone's pass once it says it is ready (app/src/inapp.ts is the other
 * half). The pass goes only to the frame this page loaded, and only at that house's origin.
 *
 * A tap on the house's name in its panel opens Houses over it (HereB-sheet): every house this phone has, how
 * each one is, and the way to add another.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { glance, reach, save, state, type House } from './houses'

const props = defineProps<{ id: string; base: string }>()
const emit = defineEmits<{ switch: [id: string]; add: []; reached: [id: string, base: string] }>()

const house = computed(() => state.houses.find(h => h.id === props.id) as House)
const base = ref(props.base)
const frame = ref<HTMLIFrameElement | null>(null)
const sheet = ref(false)
const connected = ref(false)
const src = computed(() => (base.value ? `${base.value}/?app=1` : ''))
const others = computed(() => state.houses.some(h => h.id !== props.id && (h.glance?.notes ?? 0) > 0))

function tellHouse(type: string, data: Record<string, unknown>) {
  if (!frame.value?.contentWindow || !base.value) return
  frame.value.contentWindow.postMessage({ type, ...data }, new URL(base.value).origin)
}

function onMessage(ev: MessageEvent) {
  if (!frame.value || ev.source !== frame.value.contentWindow) return
  if (!base.value || ev.origin !== new URL(base.value).origin) return      // only the house we loaded
  const m = ev.data
  if (m?.type === 'houses:ready') {
    tellHouse('houses:token', { token: house.value.token, lan: house.value.lan || null, name: house.value.name, others: others.value })
  } else if (m?.type === 'houses:status') {
    connected.value = !!m.connected
  } else if (m?.type === 'houses:open') {
    sheet.value = true
    glanceAll()
  }
}
watch(others, v => tellHouse('houses:house', { name: house.value.name, others: v }))

/* At home a house's Wi-Fi name can answer /alive and still not carry the live link (a network that lets one
   through and not the other). Eight seconds without it, and the page goes the long way round, through the
   house's own name. */
let fallback: number | undefined
watch(src, () => {
  connected.value = false
  clearTimeout(fallback)
  fallback = window.setTimeout(() => {
    if (!connected.value && base.value && base.value !== house.value.origin) base.value = house.value.origin
  }, 8000)
}, { immediate: true })

async function glanceAll() {
  await Promise.all(state.houses.map(async h => {
    if (h.reach === 'checking') { const got = await reach(h); h.reach = got.reach; emit('reached', h.id, got.base) }
    const b = h.reach === 'here' && h.lan ? `https://${h.lan}` : h.origin
    if (h.reach === 'here' || h.reach === 'away') h.glance = await glance(h, b)
  }))
}

onMounted(async () => {
  window.addEventListener('message', onMessage)
  house.value.opened = Date.now(); save(house.value)
  if (!base.value) { const got = await reach(house.value); house.value.reach = got.reach; base.value = got.base; emit('reached', props.id, got.base) }
  glanceAll()
})
onUnmounted(() => { window.removeEventListener('message', onMessage); clearTimeout(fallback) })

function line(h: House): { here: boolean; text: string; needs: boolean } {
  if (h.glance?.notes) return { here: h.reach === 'here', needs: true, text: h.glance.notes === 1 ? (h.glance.first || 'Something needs a look') : `${h.glance.notes} things need a look` }
  const where = { here: '', away: 'Away from it', 'home-only': 'Only on its Wi‑Fi', offline: 'Not answering', checking: '…' }[h.reach]
  return { here: h.reach === 'here', needs: false, text: where }
}
</script>

<template>
  <div class="hs-house">
    <iframe v-if="src" ref="frame" class="hs-frame" :src="src" :key="src" title="This house" allow="local-network-access; microphone; camera; geolocation; fullscreen" referrerpolicy="no-referrer"></iframe>
    <p class="hs-wait" v-else>Finding {{ house.name }}…</p>

    <section class="hs-sheet" v-if="sheet" role="dialog" aria-label="Houses">
      <div class="hs-sheet-head">
        <h1 class="hs-sheet-title">Houses</h1>
        <button class="hs-close" @click="sheet = false" aria-label="Close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </div>
      <ul class="hs-rows">
        <li v-for="h in state.houses" :key="h.id">
          <button class="hs-row" :class="{ here: line(h).here, needs: line(h).needs }" @click="h.id === id ? (sheet = false) : emit('switch', h.id)">
            <span class="hs-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M4 11l8-6 8 6v8a1 1 0 01-1 1H5a1 1 0 01-1-1z"/></svg></span>
            <span style="min-width: 0">
              <span class="hs-row-t">{{ h.name }}<span class="hs-row-temp" v-if="h.glance?.temp">{{ h.glance.temp }}</span></span>
              <span class="hs-row-s"><span class="here" v-if="line(h).here">You’re here</span><template v-if="line(h).here && line(h).text"> · </template><span :class="{ needs: line(h).needs }">{{ line(h).text }}</span></span>
            </span>
            <svg v-if="h.id !== id" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="color: var(--muted)"><path d="M9.5 6l6 6-6 6"/></svg>
            <span v-else></span>
          </button>
        </li>
      </ul>
      <div class="hs-rule"></div>
      <ul class="hs-rows" style="margin-top: 0">
        <li>
          <button class="hs-row" @click="emit('add')">
            <span class="hs-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></span>
            <span><span class="hs-row-t">Add a house</span><span class="hs-row-s">With the code a house’s screen shows you</span></span>
            <span></span>
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
