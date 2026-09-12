<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Device } from '../api'
import { setFan, setSense } from '../api'
import { perform, shortName, roomOf, store, isDead, notify, cap } from '../store'
import Icon from '../Icon.vue'
import DeviceArt from '../DeviceArt.vue'

/* A thermostat, laid out like the dial on the wall: the number you set large in the middle with a
   step either way, what the room is actually doing beneath it, then the modes, then the fan with
   a timer the hub keeps. In the house's unit, which follows the home's location. */
const props = defineProps<{ device: Device }>()
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const pending = computed(() => !!store.pending[props.device.id])
const name = computed(() => shortName(props.device, roomOf(props.device)))
const unit = computed(() => (store.tempUnit || '°').replace(/[^°CF]/g, ''))
const step = computed(() => unit.value.includes('F') ? 1 : 0.5)
const mode = computed(() => props.device.state)                       // heat, cool, heat_cool, off…
const off = computed(() => mode.value === 'off')
const range = computed(() => mode.value === 'heat_cool' && a.value.target_temp_low != null && a.value.target_temp_high != null)
const fmt = (t: number | null | undefined) => t == null ? '–' : String(step.value === 1 ? Math.round(t) : Math.round(t * 2) / 2)
const ACTION: Record<string, string> = { heating: 'Heating', cooling: 'Cooling', idle: 'Holding', fan: 'Fan running', drying: 'Drying', preheating: 'Warming up', defrosting: 'Defrosting' }
const MODES: Record<string, string> = { heat: 'Heat', cool: 'Cool', heat_cool: 'Auto', auto: 'Auto', off: 'Off', fan_only: 'Fan', dry: 'Dry' }
const modes = computed(() => ((a.value.hvac_modes ?? []) as string[]).filter(m => m in MODES))
/* sensing from another room: the big number is what that room should reach; the hub moves the thermostat */
const sensing = computed(() => !!a.value.sense_from && !range.value)
const shown = computed(() => sensing.value ? a.value.wanted : a.value.temperature)
/* a room sensor reads like a room: unplaced sensors, and readings no room has (a freezer, an oven), stay out */
const inHouseUnit = (v: number, from?: string) => !from ? v : from.includes('F') === unit.value.includes('F') ? v : unit.value.includes('F') ? v * 9 / 5 + 32 : (v - 32) * 5 / 9
function plausible(d: Device) {
  const v = inHouseUnit(Number(d.state), d.attrs.unit_of_measurement)
  if (!Number.isFinite(v)) return false
  return unit.value.includes('F') ? v >= 45 && v <= 95 : v >= 7 && v <= 35
}
const sensors = computed(() => {
  const own = props.device.hw
  const out: { id: string; label: string }[] = []
  for (const r of store.rooms) for (const d of r.devices) {
    if (r.id === 'unassigned' || cap(d) !== 'sensor' || !d.capability.endsWith('.temperature') || (own && d.hw === own) || isDead(d) || !plausible(d)) continue
    const same = r.devices.filter(x => x.capability === 'sensor.temperature').length > 1
    out.push({ id: d.id, label: same ? `${r.name} · ${shortName(d, r)}` : r.name })
  }
  return out
})
const senseBusy = ref(false)
async function sense(id: string | null) {
  if (senseBusy.value || (id ?? null) === (a.value.sense_from ?? null)) return
  senseBusy.value = true
  try { await setSense(props.device.id, id); notify(id ? `Sensing from ${sensors.value.find(s => s.id === id)?.label ?? 'the sensor'}.` : 'Back to the thermostat\'s own sensor.') }
  catch (e: any) { notify(`Couldn't change the sensor: ${e.message}`, 'error') }
  senseBusy.value = false
}
const doing = computed(() => {
  if (dead.value) return 'Not responding'
  const parts = sensing.value
    ? [`${a.value.sense_name} ${fmt(a.value.sense_temp)}${unit.value}`, `thermostat ${fmt(a.value.current_temperature)}${unit.value}, set to ${fmt(a.value.temperature)}${unit.value}`]
    : [`Currently ${fmt(a.value.current_temperature)}${unit.value}`]
  if (!off.value) parts.push(ACTION[a.value.hvac_action] ?? MODES[mode.value] ?? mode.value)
  if (a.value.preset_mode === 'eco') parts.push('Eco')
  if (a.value.current_humidity != null) parts.push(`${Math.round(a.value.current_humidity)}% humidity`)
  return parts.join(' · ')
})
const clamp = (t: number) => Math.min(a.value.max_temp ?? 35, Math.max(a.value.min_temp ?? 5, t))
function nudge(dir: 1 | -1) {
  if (dead.value || off.value) return
  const s = step.value * dir
  if (range.value) {
    const lo = clamp(a.value.target_temp_low + s), hi = clamp(a.value.target_temp_high + s)
    perform(props.device, 'set', { target_temp_low: lo, target_temp_high: hi }, { attrs: { target_temp_low: lo, target_temp_high: hi } })
  } else if (sensing.value) {
    const t = clamp((a.value.wanted ?? a.value.sense_temp ?? 20) + s)
    perform(props.device, 'set', { temperature: t }, { attrs: { wanted: t } })
  } else {
    const t = clamp((a.value.temperature ?? a.value.current_temperature ?? 20) + s)
    perform(props.device, 'set', { temperature: t }, { attrs: { temperature: t } })
  }
}
function setMode(m: string) { if (!dead.value && m !== mode.value) perform(props.device, 'mode', { hvac_mode: m }, { state: m }) }

/* The dial on the wall, drawn — the last device with a picture in art.ts that no tile ever showed.
   Which way the arc runs is what the house is doing, not what it was asked for: the same fallback
   the state line uses, so a thermostat set to cool but currently holding draws no arc and says
   Holding. */
const doingNow = computed(() => off.value || dead.value ? '' : a.value.hvac_action ?? mode.value)
const artState = computed(() => ({
  cooling: doingNow.value === 'cooling' || doingNow.value === 'cool',
  heating: doingNow.value === 'heating' || doingNow.value === 'heat',
}))

/* the fan: Home Assistant only knows on and off (and "on" means hours), so the hub keeps the timer */
const FAN = [{ m: 15, label: '15 min' }, { m: 30, label: '30 min' }, { m: 60, label: '1 hr' }, { m: 120, label: '2 hr' }]
const hasFan = computed(() => Array.isArray(a.value.fan_modes) && a.value.fan_modes.includes('on'))
const now = ref(Date.now())
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 15000) })
onUnmounted(() => clearInterval(tick))
const fanLeft = computed(() => a.value.fan_until ? Math.max(0, Math.round((a.value.fan_until * 1000 - now.value) / 60000)) : null)
const fanOn = computed(() => a.value.fan_mode === 'on' || (a.value.fan_until != null && a.value.fan_until * 1000 > now.value))
const fanText = computed(() => !fanOn.value ? 'Fan' : fanLeft.value != null ? `Fan · ${fanLeft.value < 1 ? 'under a minute' : fanLeft.value + ' min'} left` : 'Fan · running')
const fanBusy = ref(false)
async function fan(minutes: number) {
  if (dead.value || fanBusy.value) return
  fanBusy.value = true
  try { await setFan(props.device.id, minutes); notify(minutes ? `Fan on for ${FAN.find(f => f.m === minutes)?.label ?? minutes + ' min'}.` : 'Fan off.') }
  catch (e: any) { notify(`The fan didn't respond: ${e.message}`, 'error') }
  fanBusy.value = false
}
</script>

<template>
  <div class="tile climate wide" :class="[mode, { on: !off, dead, pending }]" :aria-label="`${name}, ${doing}`">
    <div class="tile-body">
      <div class="clim-head">
        <span class="tile-icon"><Icon name="climate" /></span>
        <span class="tile-name">{{ name }}</span>
      </div>

      <div class="clim-dial">
        <button class="clim-btn" :disabled="off || dead" @click="nudge(-1)" aria-label="Lower the target"><Icon name="minus" :size="20" /></button>
        <div class="clim-center">
          <!-- The dial goes round the number, not into a corner: this tile has no
               quiet corner, and art.ts drew it as the dial on the wall with the
               number deliberately left out for the tile to supply. -->
          <div class="clim-face">
            <DeviceArt kind="thermostat" :state="artState" fit="face" />
            <span class="clim-big" v-if="off || dead">{{ fmt(a.current_temperature) }}<span class="clim-unit">{{ unit }}</span></span>
            <span class="clim-big" v-else-if="range">{{ fmt(a.target_temp_low) }}<span class="clim-dash">–</span>{{ fmt(a.target_temp_high) }}<span class="clim-unit">{{ unit }}</span></span>
            <span class="clim-big" v-else>{{ fmt(shown) }}<span class="clim-unit">{{ unit }}</span></span>
          </div>
          <span class="clim-doing">{{ off && !dead ? `Off · ${doing}` : doing }}</span>
        </div>
        <button class="clim-btn" :disabled="off || dead" @click="nudge(1)" aria-label="Raise the target"><Icon name="plus" :size="20" /></button>
      </div>

      <div class="clim-rows" v-if="!dead">
        <div class="clim-row" v-if="modes.length > 1">
          <button v-for="m in modes" :key="m" class="clim-chip" :class="{ on: m === mode }" @click="setMode(m)">{{ MODES[m] }}</button>
        </div>
        <div class="clim-row sense" v-if="sensors.length">
          <span class="clim-fan-label"><Icon name="sensor" :size="18" />{{ range ? 'Auto uses the thermostat\'s own sensor' : 'Sensing from' }}</span>
          <template v-if="!range">
            <button class="clim-chip" :class="{ on: !a.sense_from }" :disabled="senseBusy" @click="sense(null)">Thermostat</button>
            <button v-for="s in sensors" :key="s.id" class="clim-chip" :class="{ on: a.sense_from === s.id }" :disabled="senseBusy" @click="sense(s.id)">{{ s.label }}</button>
          </template>
        </div>
        <div class="clim-row fan" v-if="hasFan" :class="{ running: fanOn }">
          <span class="clim-fan-label"><Icon name="fan" :size="20" :class="{ spin: fanOn }" />{{ fanText }}</span>
          <template v-if="fanOn"><button class="clim-chip stop" :disabled="fanBusy" @click="fan(0)">Stop</button></template>
          <template v-else><button v-for="f in FAN" :key="f.m" class="clim-chip" :disabled="fanBusy" @click="fan(f.m)">{{ f.label }}</button></template>
        </div>
      </div>
    </div>
  </div>
</template>
