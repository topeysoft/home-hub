<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { startPair, getPair, pairPin, stopPair, type Pair } from './api'
import Icon from './Icon.vue'

/* Bringing a radio device into the house: open the door, say what to press, show what joined. */
const props = defineProps<{ kind: 'zigbee' | 'zwave' | 'matter' }>()
const emit = defineEmits<{ close: [] }>()
const NAMES = { zigbee: 'Zigbee', zwave: 'Z‑Wave', matter: 'Matter' }
const pair = ref<Pair>({ state: 'idle' }), code = ref(''), pin = ref(''), busy = ref(false), error = ref('')
const live = computed(() => ['listening', 'found', 'pin', 'working'].includes(pair.value.state))
const mins = computed(() => { const s = pair.value.seconds_left; return s == null ? '' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` })
let poll: number | undefined
async function refresh() { try { pair.value = await getPair() } catch {} ; if (live.value) poll = window.setTimeout(refresh, 1500) }
async function begin() {
  if (props.kind === 'matter' && !code.value.trim()) { error.value = 'The code on the device is needed.'; return }
  busy.value = true; error.value = ''
  try { pair.value = await startPair(props.kind, props.kind === 'matter' ? code.value.trim() : undefined); refresh() }
  catch (e: any) { error.value = e.message }
  busy.value = false
}
async function sendPin() {
  busy.value = true; error.value = ''
  try { pair.value = await pairPin(pin.value.trim()); pin.value = '' } catch (e: any) { error.value = e.message }
  busy.value = false
}
async function stop() { clearTimeout(poll); try { pair.value = await stopPair() } catch {} }
async function leave() { if (live.value) await stop(); emit('close') }
onMounted(refresh)
onUnmounted(() => clearTimeout(poll))
</script>

<template>
  <div class="flow pair">
    <h3 class="flow-title">Add a {{ NAMES[kind] }} device</h3>

    <template v-if="!live && pair.state !== 'done'">
      <p class="flow-desc" v-if="kind === 'zigbee'">Zigbee things (bulbs, sensors, plugs, remotes) join when the hub opens its door. Have the device nearby and its instructions to hand; most pair by holding a button or switching them off and on a few times.</p>
      <p class="flow-desc" v-else-if="kind === 'zwave'">Z‑Wave things join when the hub opens its door. Have the device nearby; most pair with a triple-press of their button. Locks and other secured devices ask for the 5‑digit code on their sticker.</p>
      <template v-else>
        <p class="flow-desc">Matter things carry a QR code and a code printed under it, on the device or in the box. Type the printed code here. The device should be powered and in pairing mode.</p>
        <label class="field"><span class="field-label">Pairing code</span><input class="input" v-model="code" placeholder="e.g. 3497-011-2332 or MT:…" autocomplete="off" autocapitalize="characters" spellcheck="false" @keydown.enter="begin" /></label>
      </template>
      <p class="error" v-if="error">{{ error }}</p>
      <p class="flow-desc pair-last" v-if="pair.state === 'failed' || pair.state === 'closed'">{{ pair.text }}</p>
      <div class="flow-actions">
        <button class="button" :class="{ busy }" @click="begin">{{ kind === 'matter' ? 'Add it' : 'Open the door' }}</button>
        <button class="button ghost" @click="leave">Back</button>
      </div>
    </template>

    <template v-else-if="live">
      <p class="flow-desc pair-live"><span class="pulse-dot"></span>{{ pair.text }}</p>
      <p class="sheet-status" v-if="mins && pair.state === 'listening'">The door stays open for {{ mins }}.</p>
      <template v-if="pair.needs === 'pin'">
        <label class="field"><span class="field-label">5‑digit code</span><input class="input code-input" v-model="pin" inputmode="numeric" pattern="[0-9]*" maxlength="5" autocomplete="off" @keydown.enter="sendPin" /></label>
        <p class="error" v-if="error">{{ error }}</p>
        <div class="flow-actions"><button class="button" :class="{ busy }" @click="sendPin">Continue</button><button class="button ghost" @click="stop">Stop</button></div>
      </template>
      <div class="flow-actions" v-else><button class="button ghost" @click="stop">Stop</button></div>
    </template>

    <template v-else>
      <p class="flow-done"><span class="done-icon"><Icon name="check" :size="20" /></span>{{ pair.text }}</p>
      <div class="flow-actions"><button class="button" @click="begin">Add another</button><button class="button ghost" @click="leave">Done</button></div>
    </template>
  </div>
</template>
