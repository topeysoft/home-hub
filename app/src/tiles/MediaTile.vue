<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { imageUrl, type Device } from '../api'
import { perform, shortName, roomOf, store, isDead } from '../store'
import Icon from '../Icon.vue'

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
      <Icon v-else :name="isTv ? 'tv' : 'media'" :size="28" />
    </div>
    <div class="media-text">
      <span class="tile-name">{{ name }}</span>
      <span class="media-title">{{ title }}</span>
      <span class="media-sub" v-if="sub">{{ sub }}</span>
    </div>
    <div class="media-controls" v-if="!off && !dead">
      <button v-if="!isTv" class="ctl" @click="perform(device, 'previous')" aria-label="Previous"><Icon name="prev" :size="20" /></button>
      <button class="ctl primary" @click="toggle" :aria-label="playing ? 'Pause' : 'Play'"><Icon :name="playing ? 'pause' : 'play'" :size="22" /></button>
      <button v-if="!isTv" class="ctl" @click="perform(device, 'next')" aria-label="Next"><Icon name="next" :size="20" /></button>
      <label class="vol"><Icon name="volume" :size="18" />
        <input type="range" min="0" max="100" :value="volume" aria-label="Volume" @change="setVolume" />
      </label>
      <button class="ctl" @click="power" aria-label="Turn off"><Icon name="power" :size="20" /></button>
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
