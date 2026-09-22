<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { imageUrl, type Device } from '../api'
import { perform, shortName, roomOf, store, isDead } from '../store'
import Icon from '../Icon.vue'
import DeviceArt from '../DeviceArt.vue'

const props = defineProps<{ device: Device }>()
const s = computed(() => props.device.state)
const off = computed(() => s.value === 'off' || s.value === 'standby')
const dead = computed(() => isDead(props.device))
const playing = computed(() => s.value === 'playing')
const pending = computed(() => !!store.pending[props.device.id])
const isTv = computed(() => /\b(tv|television|roku|apple tv|chromecast)\b/i.test(props.device.name))
const name = computed(() => shortName(props.device, roomOf(props.device)))
const title = computed(() => props.device.attrs.media_title || (playing.value ? 'Playing' : s.value === 'paused' ? 'Paused' : off.value ? 'Off' : dead.value ? 'Not responding' : 'Idle'))
const sub = computed(() => [props.device.attrs.media_artist, props.device.attrs.app_name].filter(Boolean).join(' · '))
const volume = computed(() => Math.round((props.device.attrs.volume_level ?? 0) * 100))
/* How far through it is, for the bar the board draws beside the play button on a
   tile that has the room for one. Absent on plenty of players -- a radio stream
   has no end -- and then there is no bar rather than an empty one. */
const progress = computed(() => {
  const pos = Number(props.device.attrs.media_position), dur = Number(props.device.attrs.media_duration)
  return Number.isFinite(pos) && Number.isFinite(dur) && dur > 0 ? Math.min(100, Math.max(0, (pos / dur) * 100)) : null
})
/* the one word beside the button on a small tile: what it is doing, not what is on it */
const when = computed(() => dead.value ? 'Not responding' : playing.value ? 'Playing' : s.value === 'paused' ? 'Paused' : off.value ? 'Off' : 'Idle')

const art = ref('')
watch(() => props.device.attrs.entity_picture, (p) => { art.value = p ? imageUrl(props.device.id) : '' }, { immediate: true })

const d = () => props.device
const toggle = () => playing.value ? perform(d(), 'pause', undefined, { state: 'paused' }) : perform(d(), 'play', undefined, { state: 'playing' })
const power = () => off.value ? perform(d(), 'on', undefined, { state: 'idle' }) : perform(d(), 'off', undefined, { state: 'off' })
const setVolume = (e: Event) => { const v = Number((e.target as HTMLInputElement).value) / 100; perform(d(), 'volume', { volume_level: v }, { attrs: { volume_level: v } }) }

/* sounds: noise and rain from the hub, looped by the brain, with a sleep timer */
const sound = computed(() => (props.device.attrs.sound as string | undefined) || '')
const minutes = ref(45)
const left = computed(() => { const u = props.device.attrs.sound_until as number | undefined; if (!u) return ''; const m = Math.max(0, Math.round((u * 1000 - Date.now()) / 60000)); return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60 ? `${m % 60} min` : ''}`.trim() : `${m} min` })
const playSound = (id: string) => perform(d(), 'sound', { sound: id, minutes: minutes.value || undefined }, { state: 'playing', attrs: { sound: id } })
const stopSound = () => perform(d(), 'sound_off', undefined, { state: 'idle', attrs: { sound: null, sound_until: null } })
</script>

<template>
  <div class="tile media wide" :class="{ on: playing, off, dead, pending }">
    <div class="media-art" :class="{ has: !!art }">
      <img v-if="art" :src="art" alt="" @error="art = ''" />
      <!-- rung two, in the slot rung one would have filled: a speaker or a screen,
           drawn, rather than a 28px icon floating in an empty square -->
      <DeviceArt v-else :kind="isTv ? 'tv' : 'speaker'" :state="{ playing }" fit="slot" />
    </div>
    <!-- laid over the artwork at full height, where the words sit on it -->
    <div class="media-veil" aria-hidden="true"></div>
    <div class="media-text">
      <span class="tile-name">{{ name }}</span>
      <span class="media-title">{{ title }}</span>
      <span class="media-sub" v-if="sub">{{ sub }}</span>
    </div>
    <div class="media-controls" v-if="!off && !dead">
      <button v-if="!isTv" class="ctl" @click="perform(device, 'previous')" aria-label="Previous"><Icon name="prev" :size="20" /></button>
      <button class="ctl primary" @click="toggle" :aria-label="playing ? 'Pause' : 'Play'"><Icon :name="playing ? 'pause' : 'play'" :size="22" /></button>
      <span class="media-when">{{ when }}</span>
      <div class="media-bar" v-if="progress != null" aria-hidden="true"><i :style="{ width: progress + '%' }"></i></div>
      <button v-if="!isTv" class="ctl" @click="perform(device, 'next')" aria-label="Next"><Icon name="next" :size="20" /></button>
      <label class="vol"><Icon name="volume" :size="18" />
        <input type="range" min="0" max="100" :value="volume" aria-label="Volume" @change="setVolume" />
      </label>
      <button class="ctl power" @click="power" aria-label="Turn off"><Icon name="power" :size="20" /></button>
    </div>
    <div class="media-controls" v-else-if="!dead">
      <button class="ctl primary" @click="power" aria-label="Turn on"><Icon name="power" :size="22" /></button>
      <span class="media-hint">Tap to turn on</span>
    </div>
    <div class="sounds" v-if="!isTv && !dead && store.sounds.length">
      <button v-for="s in store.sounds" :key="s.id" class="clim-chip" :class="{ on: sound === s.id }" @click="sound === s.id ? stopSound() : playSound(s.id)">{{ s.name }}</button>
      <select class="snd-for" v-model.number="minutes" aria-label="For how long" :disabled="!!sound">
        <option :value="0">Until stopped</option><option :value="30">30 min</option><option :value="45">45 min</option><option :value="60">1 hour</option><option :value="90">1½ hours</option><option :value="480">8 hours</option>
      </select>
      <span class="snd-left" v-if="sound && left">{{ left }} left</span>
      <button v-if="sound" class="clim-chip stop" @click="stopSound">Stop</button>
    </div>
  </div>
</template>

<style scoped>
/* MediaTile's own insides. Every rule here matches something this template draws, so `scoped`
   narrows it to the elements it already applied to, and these names can no longer collide with
   another screen's by accident.

   What stayed in panel.css, deliberately: anything on the component's outermost element, because
   that is where the rest of the sheet does its cross-cutting work and scoping would make a moved
   rule outrank the ones it used to tie with; any class another component also draws, which is
   shared vocabulary rather than ours; and any rule reaching in from a container (`.bento`,
   `.wall-stage`), which belongs to the arrangement rather than to this. */

.media-sub {
  color: var(--muted);
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.media-when {
  display: none;
  font-size: 13.5px;
  color: var(--muted);
}
.media-veil {
  display: none;
}
.media-hint {
  color: var(--muted);
  font-size: 14px;
  margin-left: 4px;
}
.snd-for {
  height: 32px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--surface-hi);
  border: 1px solid var(--edge);
  color: var(--ink-2);
  font: inherit;
  font-size: 13px;
  -webkit-appearance: none;
  appearance: none;
}
.snd-for:disabled {
  opacity: 0.5;
}</style>
