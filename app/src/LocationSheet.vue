<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { searchPlaces, autoLocate, placeName, saveLocation, type Place } from './api'
import { store, notify, updateSky } from './store'
import Icon from './Icon.vue'

const q = ref(''), results = ref<Place[]>([]), pick = ref<Place | null>(store.ambient.location), status = ref(''), busy = ref('')
const canDevice = computed(() => window.isSecureContext && 'geolocation' in navigator)
const COORD = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/
let timer: number | undefined
function onInput() {
  clearTimeout(timer)
  const m = q.value.match(COORD)
  if (m) { results.value = [{ name: 'These coordinates', lat: Number(m[1]), lon: Number(m[2]) }]; return }
  if (q.value.trim().length < 2) { results.value = []; return }
  timer = window.setTimeout(async () => {
    status.value = 'Searching…'
    try { results.value = await searchPlaces(q.value.trim()); status.value = results.value.length ? '' : 'No places found. Try a bigger town nearby.' }
    catch { status.value = 'Search is not available right now.' }
  }, 350)
}
async function choose(p: Place) {
  pick.value = p; results.value = []; q.value = ''
  if (p.name === 'These coordinates') try { pick.value = await placeName(p.lat, p.lon) } catch {}
}
async function useAuto() {
  busy.value = 'auto'; status.value = 'Asking the internet where this hub is…'
  try { pick.value = await autoLocate(); status.value = 'Roughly right for the sky and weather. Search below if it is off.' }
  catch { status.value = 'Could not work it out. Search for your town instead.' }
  busy.value = ''
}
function useDevice() {
  busy.value = 'device'; status.value = 'Asking this device…'
  navigator.geolocation.getCurrentPosition(async pos => {
    const { latitude: lat, longitude: lon } = pos.coords
    try { pick.value = await placeName(lat, lon) } catch { pick.value = { name: 'This device', lat, lon } }
    status.value = ''; busy.value = ''
  }, () => { status.value = 'This device would not share its location.'; busy.value = '' }, { timeout: 12000 })
}
async function save() {
  if (!pick.value) return
  busy.value = 'save'
  try {
    const r = await saveLocation(pick.value)
    store.ambient.location = pick.value; updateSky()
    notify(r.weather ? `Home is ${pick.value.name}. Weather is on its way.` : `Home is ${pick.value.name}.`)
    close()
  } catch (e: any) { status.value = `Could not save: ${e.message}` }
  busy.value = ''
}
function close() { store.sheet = null }
function key(e: KeyboardEvent) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', key))
onUnmounted(() => window.removeEventListener('keydown', key))
const coords = (p: Place) => `${p.lat.toFixed(3)}, ${p.lon.toFixed(3)}`
</script>

<template>
  <div class="sheet-back" @click.self="close">
    <div class="sheet" role="dialog" aria-label="Home location">
      <button class="round sheet-close" @click="close" aria-label="Close"><Icon name="close" :size="20" /></button>
      <h2 class="display">Where is home?</h2>
      <p class="sheet-lede">The sky, sunrise and weather follow this. It stays on the hub and is never shared.</p>

      <div class="loc-actions">
        <button v-if="canDevice" class="button" :class="{ busy: busy === 'device' }" @click="useDevice"><Icon name="target" :size="18" /> Use this device's location</button>
        <button class="button ghost" :class="{ busy: busy === 'auto' }" @click="useAuto"><Icon name="refresh" :size="18" /> Find it automatically</button>
      </div>

      <label class="search">
        <Icon name="search" :size="18" />
        <input v-model="q" @input="onInput" type="search" placeholder="Search a town, or type coordinates" autocomplete="off" spellcheck="false" />
      </label>
      <ul class="results" v-if="results.length">
        <li v-for="r in results" :key="r.name + r.lat"><button @click="choose(r)"><span class="r-name">{{ r.name }}</span><span class="r-sub">{{ coords(r) }}</span></button></li>
      </ul>
      <p class="sheet-status" v-if="status">{{ status }}</p>

      <div class="chosen" v-if="pick">
        <Icon name="pin" :size="20" />
        <span class="chosen-text"><span class="r-name">{{ pick.name }}</span><span class="r-sub">{{ coords(pick) }}</span></span>
        <button class="button" :class="{ busy: busy === 'save' }" @click="save">{{ store.ambient.location ? 'Save' : 'Use this' }}</button>
      </div>
    </div>
  </div>
</template>
