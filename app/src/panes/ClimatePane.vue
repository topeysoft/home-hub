<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * The dial, which is the one instrument in the house that is a number you SET rather than a level
 * you drag — so it is the one place a ring earns its keep: the white handle is what was asked for,
 * the colored arc is the gap the box is closing, and the number in the middle is the answer to
 * "what did I set it to", which the old pane could not tell you at all.
 *
 * Every control here already existed in the brain (set, mode, the fan timer, sensing from another
 * room's thermometer). None of them could be reached from the panel until this pane.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Device } from '../api'
import { setFan, setSense } from '../api'
import { cap, isDead, notify, perform, shortName, store } from '../store'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const a = computed(() => props.device.attrs)
const dead = computed(() => isDead(props.device))
const unit = computed(() => (store.tempUnit || '°').replace(/[^°CF]/g, '') || '°')
const step = computed(() => unit.value.includes('F') ? 1 : 0.5)
const mode = computed(() => props.device.state)
const off = computed(() => mode.value === 'off')
const fmt = (t: number | null | undefined) => t == null ? '–' : String(step.value === 1 ? Math.round(t) : Math.round(t * 2) / 2)

const MODES: Record<string, string> = { heat: 'Warm it', cool: 'Cool it', heat_cool: 'Either', auto: 'Either', off: 'Off', fan_only: 'Fan only', dry: 'Dry' }
const ACTION: Record<string, string> = { heating: 'Warming', cooling: 'Cooling', idle: 'Holding', fan: 'Fan running', drying: 'Drying', preheating: 'Warming up', defrosting: 'Defrosting' }
const modes = computed(() => ((a.value.hvac_modes ?? []) as string[]).filter(m => m in MODES))
const sensing = computed(() => !!a.value.sense_from)
const target = computed(() => sensing.value ? a.value.wanted ?? a.value.temperature : a.value.temperature)
const current = computed(() => sensing.value ? a.value.sense_temp ?? a.value.current_temperature : a.value.current_temperature)
const doing = computed(() => dead.value ? 'Not answering' : off.value ? 'Off' : `${ACTION[a.value.hvac_action] ?? MODES[mode.value] ?? mode.value} · ${fmt(current.value)}${unit.value} in here now`)

/* The ring: 270 degrees from the bottom left, over the span a house thermostat is actually set
   across. Where the dial cannot say (no target yet) nothing is drawn rather than a guess. */
const LOW = computed(() => a.value.min_temp ?? (unit.value.includes('F') ? 50 : 10))
const HIGH = computed(() => a.value.max_temp ?? (unit.value.includes('F') ? 90 : 32))
const R = 132, SWEEP = 0.75, C = 2 * Math.PI * R
const along = (t: number | null | undefined) => t == null ? null
  : Math.min(1, Math.max(0, (t - LOW.value) / (HIGH.value - LOW.value))) * SWEEP * C
const arc = computed(() => {
  const t = along(showing.value), c = along(current.value)
  if (t == null || c == null) return null
  return { from: Math.min(t, c), len: Math.max(2, Math.abs(t - c)), warm: (target.value ?? 0) > (current.value ?? 0) }
})
const handle = computed(() => along(showing.value))

const clamp = (t: number) => Math.min(HIGH.value, Math.max(LOW.value, t))
const round = (t: number) => step.value === 1 ? Math.round(t) : Math.round(t * 2) / 2

/* Dragging the ring.
 *
 * The two buttons are for a degree at a time; the ring is for crossing four of them, and it is what
 * a hand reaches for first -- which is the whole reason a dial was drawn rather than a row of
 * numbers. What the finger is doing shows in the middle of the dial while it is down, and the house
 * is told once, on the way up: a drag across the arc is fifty pointermoves and a thermostat that is
 * told fifty times will queue them and arrive somewhere else entirely.
 *
 * The angles are the ring's own: the track starts at 135 degrees (bottom left) and sweeps 270 of
 * them clockwise, so the 90 degrees at the bottom are a gap. A finger that lands in the gap gets
 * the end it is nearer rather than nothing, because a thumb aiming for "all the way down" lands
 * there every time.
 */
const dial = ref<HTMLElement | null>(null)
const held = ref<number | null>(null)          // what the finger is asking for, while it is down
const showing = computed(() => held.value ?? target.value)

function tempAt(e: PointerEvent): number | null {
  const el = dial.value
  if (!el) return null
  const r = el.getBoundingClientRect()
  const a = (Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180 / Math.PI + 360) % 360
  let f = ((a - 135 + 360) % 360) / 270
  if (f > 1) f = a < 90 ? 1 : 0                // in the gap at the bottom: the nearer end
  return clamp(round(LOW.value + f * (HIGH.value - LOW.value)))
}
function grab(e: PointerEvent) {
  if (off.value || dead.value || (e.target as HTMLElement).closest('button')) return
  try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) } catch { /* a mouse in a test has no capture */ }
  held.value = tempAt(e)
}
function turn(e: PointerEvent) { if (held.value != null) held.value = tempAt(e) }
function letGo() {
  const t = held.value
  held.value = null
  if (t == null || t === target.value) return
  perform(props.device, 'set', { temperature: t }, { attrs: sensing.value ? { wanted: t } : { temperature: t } })
}
function key(e: KeyboardEvent) {
  const d = e.key === 'ArrowUp' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowDown' || e.key === 'ArrowLeft' ? -1 : 0
  if (!d) return
  e.preventDefault()
  nudge(d as 1 | -1)
}

function nudge(dir: 1 | -1) {
  if (dead.value || off.value) return
  const t = clamp(round((target.value ?? current.value ?? 20) + step.value * dir))
  perform(props.device, 'set', { temperature: t }, { attrs: sensing.value ? { wanted: t } : { temperature: t } })
}
const setMode = (m: string) => { if (!dead.value && m !== mode.value) perform(props.device, 'mode', { hvac_mode: m }, { state: m }) }

/* The fan, and the timer the hub keeps for it because Home Assistant's "on" means hours. Three
   lengths rather than the tile's four: the row is a card here, and a quarter of an hour of fan is
   the one nobody picks. */
const FAN = [30, 60, 120]
const hasFan = computed(() => Array.isArray(a.value.fan_modes) && a.value.fan_modes.includes('on'))
const now = ref(Date.now())
let tick: number | undefined
onMounted(() => { tick = window.setInterval(() => (now.value = Date.now()), 15000) })
onUnmounted(() => clearInterval(tick))
const fanOn = computed(() => a.value.fan_mode === 'on' || (a.value.fan_until != null && a.value.fan_until * 1000 > now.value))
const fanLeft = computed(() => a.value.fan_until ? Math.max(0, Math.round((a.value.fan_until * 1000 - now.value) / 60000)) : null)
const busy = ref(false)
async function fan(minutes: number) {
  if (dead.value || busy.value) return
  busy.value = true
  try { await setFan(props.device.id, minutes); notify(minutes ? `Fan on for ${minutes < 60 ? `${minutes} min` : `${minutes / 60} h`}.` : 'Fan off.') }
  catch (e: any) { notify(`The fan didn't respond: ${e.message}`, 'error') }
  busy.value = false
}

/* which thermometer it goes by: the pane where that decision belongs, since it is this box that
   acts on it. Only rooms with a sensible reading are offered, exactly as the tile does. */
const inHouseUnit = (v: number, from?: string) => !from ? v : from.includes('F') === unit.value.includes('F') ? v : unit.value.includes('F') ? v * 9 / 5 + 32 : (v - 32) * 5 / 9
function plausible(d: Device) {
  const v = inHouseUnit(Number(d.state), d.attrs.unit_of_measurement)
  if (!Number.isFinite(v)) return false
  return unit.value.includes('F') ? v >= 45 && v <= 95 : v >= 7 && v <= 35
}
const sensors = computed(() => {
  const own = props.device.hw, out: { id: string; label: string }[] = []
  for (const r of store.rooms) for (const d of r.devices) {
    if (r.id === 'unassigned' || cap(d) !== 'sensor' || !d.capability.endsWith('.temperature') || (own && d.hw === own) || isDead(d) || !plausible(d)) continue
    const same = r.devices.filter(x => x.capability === 'sensor.temperature').length > 1
    out.push({ id: d.id, label: same ? `${r.name} · ${shortName(d, r)}` : r.name })
  }
  return out
})
async function sense(id: string | null) {
  if (busy.value || (id ?? null) === (a.value.sense_from ?? null)) return
  busy.value = true
  try { await setSense(props.device.id, id); notify(id ? `Going by ${sensors.value.find(s => s.id === id)?.label ?? 'that sensor'}.` : 'Back to its own sensor.') }
  catch (e: any) { notify(`Couldn't change the sensor: ${e.message}`, 'error') }
  busy.value = false
}
</script>

<template>
  <div class="rig rig-climate">
    <div class="rig-dial" ref="dial" :class="{ turning: held != null, still: off || dead }"
         role="slider" tabindex="0" :aria-label="`${device.name}, what to ask for`"
         :aria-valuemin="LOW" :aria-valuemax="HIGH" :aria-valuenow="showing ?? current"
         @pointerdown="grab" @pointermove="turn" @pointerup="letGo" @pointercancel="letGo" @keydown="key">
      <svg viewBox="0 0 330 330" class="rig-ring" aria-hidden="true">
        <circle cx="165" cy="165" :r="R" fill="none" stroke="rgba(255,255,255,.10)" stroke-width="17" stroke-linecap="round"
                :stroke-dasharray="`${SWEEP * C} ${C}`" transform="rotate(135 165 165)" />
        <circle v-if="arc && !off" cx="165" cy="165" :r="R" fill="none" :stroke="arc.warm ? 'var(--lamp)' : '#7ab0e8'" stroke-width="17" stroke-linecap="round"
                :stroke-dasharray="`${arc.len} ${C}`" :stroke-dashoffset="-arc.from" transform="rotate(135 165 165)" />
        <circle v-if="handle != null && !off" cx="165" cy="165" :r="R" fill="none" stroke="#f1eee8" stroke-width="25" stroke-linecap="round"
                :stroke-dasharray="`6 ${C}`" :stroke-dashoffset="-handle" transform="rotate(135 165 165)" />
      </svg>
      <div class="rig-dial-face">
        <span class="display rig-dial-n">{{ off ? fmt(current) : fmt(showing) }}<i>{{ unit }}</i></span>
        <span class="rig-lbl">{{ off ? 'In here now' : 'Asked for' }}</span>
        <span class="rig-dial-doing">{{ held != null ? 'Let go to ask for it' : doing }}</span>
      </div>
      <button class="ctl rig-dial-btn low" :disabled="off || dead" @click="nudge(-1)" aria-label="Lower it"><Icon name="minus" :size="26" /></button>
      <button class="ctl rig-dial-btn high" :disabled="off || dead" @click="nudge(1)" aria-label="Raise it"><Icon name="plus" :size="26" /></button>
    </div>

    <div class="rig-side">
      <div v-if="modes.length > 1">
        <span class="rig-lbl">What it should do</span>
        <div class="rig-modes">
          <button v-for="m in modes" :key="m" class="rig-mode" :class="{ on: m === mode }" :disabled="dead" @click="setMode(m)">{{ MODES[m] }}</button>
        </div>
      </div>

      <div class="rig-row" v-if="hasFan">
        <span class="rig-row-head"><Icon name="fan" :size="20" :class="{ spin: fanOn }" />
          {{ fanOn ? (fanLeft ? `Fan · ${fanLeft} min` : 'Fan running') : 'Fan for' }}</span>
        <div class="rig-row-acts">
          <button v-if="fanOn" class="clim-chip stop" :disabled="busy" @click="fan(0)">Stop</button>
          <button v-else v-for="m in FAN" :key="m" class="clim-chip" :disabled="busy" @click="fan(m)">{{ m < 60 ? `${m}m` : `${m / 60}h` }}</button>
        </div>
      </div>

      <div class="rig-row" v-if="sensors.length">
        <span class="rig-row-head"><Icon name="sensor" :size="19" />Going by</span>
        <div class="rig-row-acts">
          <button class="clim-chip" :class="{ on: !a.sense_from }" :disabled="busy" @click="sense(null)">Its own</button>
          <button v-for="s in sensors" :key="s.id" class="clim-chip" :class="{ on: a.sense_from === s.id }" :disabled="busy" @click="sense(s.id)">{{ s.label }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ClimatePane's own insides. Every rule here matches something this template draws, so `scoped`
   narrows it to the elements it already applied to, and these names can no longer collide with
   another screen's by accident.

   What stayed in panel.css, deliberately: anything on the component's outermost element, because
   that is where the rest of the sheet does its cross-cutting work and scoping would make a moved
   rule outrank the ones it used to tie with; any class another component also draws, which is
   shared vocabulary rather than ours; and any rule reaching in from a container (`.bento`,
   `.wall-stage`), which belongs to the arrangement rather than to this. */

.rig-dial-doing {
  margin-top: 16px;
  font-size: 15px;
  color: var(--ink-2);
}
.rig-dial-btn {
  position: absolute;
  bottom: 0;
  width: 68px;
  height: 68px;
}
.rig-dial-btn.low {
  left: 0;
}
.rig-dial-btn.high {
  right: 0;
}
.rig-side {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
  justify-content: center;
}
.rig-modes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.rig-mode {
  height: 48px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: var(--surface-hi);
  color: var(--ink-2);
  font: inherit;
  font-size: 15.5px;
  /* a chip, not a row: `button { text-align: left }` at the top of this file governs every button in
     the panel, and these are the artboard's centered pills */
  text-align: center;
  cursor: pointer;
  transition: background 0.15s var(--ease);
}
.rig-mode:hover {
  background: var(--surface-press);
}
.rig-mode.on {
  border-color: rgba(122, 176, 232, 0.45);
}
.rig-mode.on {
  background: rgba(122, 176, 232, 0.22);
  color: #d6e8fb;
}
.rig-row {
  /* one surface with the choice inside it, the way the board drew the fan and the sensor: a loose
     label above loose chips read as a settings list rather than as part of the dial */
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 62px;
  padding: 10px 16px;
  border-radius: 20px;
  border: 1px solid var(--edge);
  background: rgba(255, 255, 255, 0.05);
}
.rig-row-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
  font-size: 15.5px;
  color: var(--ink-2);
  white-space: nowrap;
}</style>
