<script setup lang="ts">
/*
 * What is playing, at the size it deserves.
 *
 * Nothing here is new to the house: the artwork, the title, the app, the volume and how far through
 * it is all arrive in the payload the panel already holds. The old pane kept one of them and drew a
 * 260px speaker outline in the empty half. So this instrument is mostly a matter of spending what
 * is already there — and the position bar ticks on its own between updates, because a player that
 * reports every ten seconds otherwise looks stuck.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { imageUrl, type Device } from '../api'
import { isDead, perform, store } from '../store'
import Icon from '../Icon.vue'
import DeviceArt from '../DeviceArt.vue'
import { useSlide } from './slide'

const props = defineProps<{ device: Device }>()
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const playing = computed(() => props.device.state === 'playing')
const off = computed(() => props.device.state === 'off' || props.device.state === 'standby')
const isTv = computed(() => /\b(tv|television|roku|apple tv|chromecast)\b/i.test(props.device.name))

const art = ref('')
watch(() => a.value.entity_picture, p => { art.value = p ? imageUrl(props.device.id) : '' }, { immediate: true })

/* where it is up to: the brain's number, carried forward by the clock while it is playing */
const ticked = ref(0)
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (ticked.value += 1), 1000) })
onUnmounted(() => clearInterval(tick))
watch(() => a.value.media_position, () => (ticked.value = 0))
const position = computed(() => {
  const p = Number(a.value.media_position)
  return Number.isFinite(p) ? p + (playing.value ? ticked.value : 0) : null
})
const duration = computed(() => { const d = Number(a.value.media_duration); return Number.isFinite(d) && d > 0 ? d : null })
const through = computed(() => position.value != null && duration.value ? Math.min(100, (position.value / duration.value) * 100) : null)
const clock = (s: number) => {
  const t = Math.max(0, Math.round(s)), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}
const left = computed(() => position.value != null && duration.value ? `${Math.max(1, Math.round((duration.value - position.value) / 60))} min left` : '')

const volume = computed(() => Math.round((a.value.volume_level ?? 0) * 100))
const setVolume = (v: number) => perform(props.device, 'volume', { volume_level: v / 100 }, { attrs: { volume_level: v / 100 } })
const vol = useSlide({
  vertical: false,
  live: v => (props.device.attrs = { ...a.value, volume_level: v / 100 }),
  settle: v => { setVolume(v) },
})
const toggle = () => playing.value ? perform(props.device, 'pause', undefined, { state: 'paused' }) : perform(props.device, 'play', undefined, { state: 'playing' })

/* a speaker is not a television: the noises the hub can play are the thing a bedside speaker is
   actually for, and a TV has no use for them */
const sound = computed(() => (a.value.sound as string | undefined) || '')
const playSound = (id: string) => perform(props.device, 'sound', { sound: id }, { state: 'playing', attrs: { sound: id } })
const stopSound = () => perform(props.device, 'sound_off', undefined, { state: 'idle', attrs: { sound: null, sound_until: null } })
</script>

<template>
  <div class="rig rig-media">
    <div class="rig-art" :class="{ has: !!art }">
      <img v-if="art" :src="art" alt="" @error="art = ''" />
      <DeviceArt v-else :kind="isTv ? 'tv' : 'speaker'" :state="{ playing }" fit="slot" />
    </div>

    <div class="rig-play">
      <div class="rig-chips" v-if="a.app_name || a.media_artist">
        <span class="rig-chip app" v-if="a.app_name">{{ a.app_name }}</span>
        <span class="rig-chip" v-if="a.media_artist">{{ a.media_artist }}</span>
      </div>

      <div class="rig-through" v-if="through != null">
        <div class="rig-bar"><i :style="{ width: through + '%' }"></i></div>
        <div class="rig-times"><span>{{ clock(position!) }}</span><span>{{ left }}</span></div>
      </div>

      <div class="rig-transport" v-if="!off && !dead">
        <button class="ctl" v-if="!isTv" @click="perform(device, 'previous')" aria-label="Skip back"><Icon name="prev" :size="24" /></button>
        <button class="ctl primary big" @click="toggle" :aria-label="playing ? 'Pause' : 'Play'"><Icon :name="playing ? 'pause' : 'play'" :size="30" /></button>
        <button class="ctl" v-if="!isTv" @click="perform(device, 'next')" aria-label="Skip on"><Icon name="next" :size="24" /></button>
      </div>
      <div class="rig-transport" v-else-if="!dead">
        <button class="ctl primary big" @click="perform(device, 'on', undefined, { state: 'idle' })" aria-label="Turn it on"><Icon name="power" :size="28" /></button>
        <span class="rig-hint">It is off. Turn it on to see what is on it.</span>
      </div>

      <div class="rig-volume" v-if="!off && !dead && a.volume_level != null">
        <Icon name="volume" :size="22" />
        <div class="rig-slider" role="slider" :aria-label="`${device.name} volume`" tabindex="0" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="volume"
             @pointerdown="vol.down" @pointermove="vol.move" @pointerup="vol.up" @pointercancel="vol.cancel" @keydown="e => vol.key(e, volume)">
          <span class="rig-slider-fill" :style="{ width: volume + '%' }"></span>
          <span class="rig-slider-knob" :style="{ left: volume + '%' }"></span>
        </div>
        <span class="rig-volume-n">{{ volume }}%</span>
      </div>

      <div class="rig-sounds" v-if="!isTv && !dead && store.sounds.length">
        <button v-for="s in store.sounds.slice(0, 5)" :key="s.id" class="clim-chip" :class="{ on: sound === s.id }"
                @click="sound === s.id ? stopSound() : playSound(s.id)">{{ s.name }}</button>
      </div>
    </div>
  </div>
</template>
