<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { act, imageUrl, type Device } from '../api'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const emit = defineEmits<{ error: [msg: string] }>()

const s = computed(() => props.device.state)
const off = computed(() => s.value === 'off' || s.value === 'standby')
const dead = computed(() => s.value === 'unavailable' || s.value === 'unknown')
const playing = computed(() => s.value === 'playing')
const isTv = computed(() => /\btv\b/i.test(props.device.name))
const title = computed(() => props.device.attrs.media_title || (playing.value ? 'Playing' : s.value === 'paused' ? 'Paused' : off.value ? 'Off' : dead.value ? 'Unreachable' : 'Idle'))
const sub = computed(() => [props.device.attrs.media_artist, props.device.attrs.app_name].filter(Boolean).join(' · '))
const volume = computed(() => Math.round((props.device.attrs.volume_level ?? 0) * 100))

const art = ref('')
watch(() => props.device.attrs.entity_picture, (p) => { art.value = p ? imageUrl(props.device.id) : '' }, { immediate: true })

async function run(action: string, data?: Record<string, unknown>) {
  try { await act(props.device.id, action, data) } catch (e: any) { emit('error', `${props.device.name}: ${e.message}`) }
}
</script>

<template>
  <div class="tile media wide" :class="{ on: playing, off, dead }">
    <div class="media-art" :class="{ has: !!art }">
      <img v-if="art" :src="art" alt="" @error="art = ''" />
      <Icon v-else :name="isTv ? 'tv' : 'media'" :size="28" />
    </div>
    <div class="media-text">
      <span class="tile-name">{{ device.name }}</span>
      <span class="media-title">{{ title }}</span>
      <span class="media-sub" v-if="sub">{{ sub }}</span>
    </div>
    <div class="media-controls" v-if="!off && !dead">
      <button class="ctl" @click="run('previous')" aria-label="Previous"><Icon name="prev" :size="20" /></button>
      <button class="ctl primary" @click="run(playing ? 'pause' : 'play')" :aria-label="playing ? 'Pause' : 'Play'"><Icon :name="playing ? 'pause' : 'play'" :size="22" /></button>
      <button class="ctl" @click="run('next')" aria-label="Next"><Icon name="next" :size="20" /></button>
      <label class="vol"><Icon name="volume" :size="18" />
        <input type="range" min="0" max="100" :value="volume" aria-label="Volume"
               @change="run('volume', { volume_level: Number(($event.target as HTMLInputElement).value) / 100 })" />
      </label>
      <button class="ctl" @click="run('off')" aria-label="Turn off"><Icon name="power" :size="20" /></button>
    </div>
    <div class="media-controls" v-else-if="!dead">
      <button class="ctl primary" @click="run('on')" aria-label="Turn on"><Icon name="power" :size="22" /></button>
    </div>
  </div>
</template>
