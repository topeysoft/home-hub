<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * One printer, opened in place: design/printers/Pane.dc.html, and PhonePaneB for the phone's sheet.
 *
 * It is a device's pane in everything but what is in it -- the same rise, the same veil, the same two
 * columns at the same place on the wall -- because a printer is a thing in the house like a lamp is, and
 * a household should not have to learn a second kind of screen to look at one. Opened.vue is the
 * original and this borrows its frame by class rather than by component: Opened is built around a
 * device from the house's model, and a printer is not one of those (brain/hub/printers.py).
 *
 * The left column is what the printer is doing, in its own words: where it is, its name, what it is
 * doing, how far as the largest thing on the screen, when it will be done, and the three temperatures --
 * in Celsius with the C written, because a nozzle at 428 degrees means nothing to anybody who prints and
 * the C makes the exception visible rather than silent. Under them, the printer's own actions as it
 * offers them, and nothing else: Stop asks twice, because a stopped print cannot be picked up again.
 *
 * The right is the camera, large, and the job. Under them the hub's limit is said once, plainly, where
 * somebody would look for a Start button: starting a print, and saying the bed is clear, happen at the
 * printer.
 *
 * THE ROOM LINE is where every pane has it, above the name. A printer starts with none, so it reads
 * "No room · Choose"; Choose turns the head into the room picker every light's pane uses, with No room at
 * the top, because a printer -- unlike a lamp -- is allowed to have none and to go back to none
 * (design/printers/RoomChoiceB). It is never asked when a printer is added.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { addRoom, printerAction, setPrinterRoom, type Printer, type PrinterAction } from './api'
import { apiUrl } from './door'
import { clockNow, notify, printerById, store } from './store'
import { actionLabel, asksTwice, doneAt, finishedLine, jobLine, layerLine, percent, swatch, timeLeft, wallActions } from './printers'
import { locale } from './lang'
import Icon from './Icon.vue'

const p = computed<Printer | null>(() => printerById(store.printer))
const shown = ref(false)
const closing = ref(false)
function close() { shown.value = false; closing.value = true; setTimeout(() => (store.printer = null), 320) }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') { if (editing.value) editing.value = false; else close() } }
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => (shown.value = true)))   // two frames: Opened.vue says why
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
/* A printer forgotten from another screen while this was open: there is nothing left to show. */
watch(p, v => { if (!v && !closing.value) close() })

const pct = computed(() => p.value ? percent(p.value) : null)
const going = computed(() => !!p.value?.job && ['preparing', 'printing', 'needs_you'].includes(p.value.state ?? ''))
/* What it is doing, in one line: "Printing Phone stand", or the printer's own headline. */
const doing = computed(() => {
  const v = p.value; if (!v) return ''
  if (v.state === 'printing' && v.job?.name) return `Printing ${v.job.name}`
  return v.headline || (v.connected ? '' : 'Not answering')
})
const tone = computed(() => ({ printing: 'live', preparing: 'live', needs_you: 'lamp', problem: 'danger', finished: 'live' } as Record<string, string>)[p.value?.state ?? ''] ?? '')
const temps = computed(() => {
  const t = p.value?.temps ?? {}
  return ([['Nozzle', t.nozzle], ['Bed', t.bed], ['Chamber', t.chamber]] as const).filter(([, v]) => v != null).map(([k, v]) => ({ k, v: Math.round(v as number) }))
})

/* ---------- the printer's own actions ---------- */
const busy = ref('')
const arming = ref('')       // the action whose question is up, waiting for the second tap
async function act(a: PrinterAction) {
  const v = p.value; if (!v || busy.value) return
  if (asksTwice(a) && arming.value !== a.id) { arming.value = a.id; return }
  arming.value = ''
  busy.value = a.id
  try {
    const next = await printerAction(v.id, a.id, a.args)
    /* The printer answered with what it is now, so the pane says that at once -- Pause turns into the
       printer's "Paused." with its own Carry on -- rather than waiting for the stream to catch up. */
    const list = store.printers?.printers
    const i = list?.findIndex(x => x.id === next.id) ?? -1
    if (list && i >= 0) list[i] = next
  } catch (e: any) { notify(e.message, 'error') }
  busy.value = ''
}

/* ---------- where it lives ---------- */
const editing = ref(false), saving = ref(false)
const newRoom = ref(''), roomName = ref('')
const rooms = computed(() => store.rooms.filter(r => r.id !== 'unassigned'))
function startEdit() { newRoom.value = p.value?.room?.id ?? ''; roomName.value = ''; editing.value = true }
async function saveEdit() {
  const v = p.value; if (!v || saving.value) return
  saving.value = true
  try {
    let room: string | null = newRoom.value || null
    /* A new room, the sort page's way of making one: named here, made, and the printer put in it. */
    if (room === '__new') {
      const n = roomName.value.trim(); if (!n) { saving.value = false; return }
      const made = await addRoom(n)
      store.rooms.push({ id: made.id, name: made.name, devices: [], intent: 'unknown' })
      room = made.id
    }
    if (room !== (v.room?.id ?? null)) {
      const next = await setPrinterRoom(v.id, room)
      v.room = next.room ?? null
      notify(v.room ? `${v.name} is in the ${v.room.name} now.` : `${v.name} has no room now.`)
    }
    editing.value = false
  } catch (e: any) { notify(e.message, 'error') }
  saving.value = false
}

const camOk = ref(true)
const thumbOk = ref(true)
</script>

<template>
  <div class="opened print-pane-shell" :class="{ shown, closing }" v-if="p" role="dialog" :aria-label="p.name">
    <div class="opened-veil" @click="close"></div>
    <div class="opened-panel" data-cap="printer">
      <button class="back opened-close" @click="close" aria-label="Close"><Icon name="close" :size="18" /></button>

      <div class="opened-body pane-body print-pane">
        <div class="pane-said">
          <div class="opened-step s0">
            <template v-if="!editing">
              <div class="opened-room print-room">
                <template v-if="p.room"><button class="print-choose" @click="startEdit" :aria-label="`${p.room.name}. Change the room`">{{ p.room.name }}</button></template>
                <template v-else>No room · <button class="print-choose" @click="startEdit">Choose</button></template>
              </div>
              <h2 class="display opened-name">{{ p.name }}</h2>
            </template>
            <!-- the pane's own edit head (Opened.vue): the room, as a picker, with No room at the top -->
            <form class="opened-edit" v-else @submit.prevent="saveEdit">
              <select class="sort-room opened-edit-room" v-model="newRoom" aria-label="Room">
                <option value="">No room</option>
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
                <option value="__new">A new room…</option>
              </select>
              <input class="opened-edit-name" v-if="newRoom === '__new'" v-model="roomName" placeholder="Name the room" spellcheck="false" aria-label="The new room's name" autofocus />
              <h2 class="display opened-name" v-else>{{ p.name }}</h2>
              <p class="opened-edit-note">Its name is {{ p.name }}’s own, and is changed at the printer.</p>
              <div class="opened-edit-acts">
                <button type="submit" class="button small" :disabled="saving || (newRoom === '__new' && !roomName.trim())">Done</button>
                <button type="button" class="button small ghost" :disabled="saving" @click="editing = false">Cancel</button>
              </div>
            </form>
            <p class="print-doing" :class="tone"><i v-if="tone"></i>{{ doing }}</p>
            <p class="print-pane-detail" v-if="p.detail && p.state !== 'printing'">{{ p.detail }}</p>
          </div>

          <div class="opened-step s1" v-if="going">
            <div class="print-pane-how">
              <span class="print-pane-pct display">{{ pct ?? 0 }}%</span>
              <span class="print-when" v-if="p.job?.remaining_s != null || p.job?.eta_clock">Done at<b>{{ doneAt(p, clockNow(), locale()) }}</b></span>
            </div>
            <div class="print-bar"><i :style="{ width: `${pct ?? 0}%` }"></i></div>
            <div class="print-foot"><span>{{ layerLine(p) }}</span><span>{{ timeLeft(p) }}</span></div>
          </div>
          <p class="opened-step s1 print-finished" v-else-if="p.state === 'finished' && finishedLine(p, locale())"><Icon name="check" :size="16" />{{ finishedLine(p, locale()) }}</p>

          <div class="opened-step s2 print-temps" v-if="temps.length">
            <div class="print-temp" v-for="t in temps" :key="t.k"><small>{{ t.k }}</small><b>{{ t.v }}°<em>C</em></b></div>
          </div>

          <div class="opened-step s3 print-acts" v-if="wallActions(p).length">
            <template v-if="arming">
              <p class="print-ask">Stop {{ p.job?.name || 'the print' }}? A stopped print can’t be picked up again.</p>
              <button class="button small danger" :class="{ busy: !!busy }" @click="act(wallActions(p).find(a => a.id === arming)!)">Yes, stop it</button>
              <button class="button small ghost" @click="arming = ''">Keep printing</button>
            </template>
            <template v-else>
              <button v-for="a in wallActions(p)" :key="a.id" class="print-act" :class="[a.id, { primary: a.primary, busy: busy === a.id }]"
                      :disabled="!!busy" @click="act(a)">
                <Icon v-if="a.id === 'pause'" name="pause" :size="16" /><Icon v-else-if="a.id === 'cancel'" name="stop" :size="16" /><Icon v-else-if="a.id === 'swap_slot'" name="swap" :size="16" />{{ actionLabel(a) }}
              </button>
            </template>
          </div>
        </div>

        <!-- the camera, large, and what is being printed; then the hub's limit, said once -->
        <div class="print-pane-look opened-step s2">
          <div class="print-pane-cam">
            <img v-if="camOk" :src="apiUrl(p.camera)" alt="" @error="camOk = false" />
            <img v-else-if="p.job?.thumbnail && thumbOk" class="print-cam-part" :src="apiUrl(p.job.thumbnail)" alt="" @error="thumbOk = false" />
            <span class="print-pane-nocam" v-else><Icon name="camera" :size="22" />No picture from {{ p.name }}’s camera</span>
            <span class="print-chip" v-if="camOk"><i></i>Live</span>
          </div>
          <div class="print-job" v-if="p.job">
            <span class="print-thumb"><img v-if="p.job.thumbnail && thumbOk" :src="apiUrl(p.job.thumbnail)" alt="" @error="thumbOk = false" /><Icon v-else name="printer" :size="20" /></span>
            <span class="print-names"><span class="print-part">{{ p.job.name }}</span><span class="print-sub">{{ jobLine(p, clockNow(), locale()) }}</span></span>
            <span class="print-swatch" v-if="swatch(p)" :style="{ background: swatch(p)! }" :aria-label="p.job.filament ?? ''"></span>
          </div>
          <p class="print-limit"><span class="print-limit-wide">Starting a print, and saying the bed is clear, happen at {{ p.name }}.</span><span class="print-limit-narrow">Starting a print happens at {{ p.name }}.</span></p>
        </div>
      </div>
    </div>
  </div>
</template>
