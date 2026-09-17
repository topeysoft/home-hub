<script setup lang="ts">
/*
 * A machine's instrument: its features, one row each, the same rows its card draws. A fridge has no
 * one switch to offer, so the rows ARE the control -- tap to switch a feature, and the reading above
 * counts what is running. Read off the features live, so the sheet stays true under the finger.
 */
import { computed } from 'vue'
import type { Device } from '../api'
import { iconFor, isDead, perform, roomOf, store } from '../store'
import { featureName, partsOfMachine } from '../machines'
import Icon from '../Icon.vue'

const props = defineProps<{ device: Device }>()
const parts = computed(() => partsOfMachine(props.device))
const room = computed(() => roomOf(props.device))
const on = (d: Device) => d.state === 'on'
function tap(d: Device) {
  if (isDead(d)) return
  perform(d, on(d) ? 'off' : 'on', undefined, { state: on(d) ? 'off' : 'on' })
}
</script>

<template>
  <div class="rig rig-machine">
    <div class="machine-rows big">
      <button v-for="d in parts" :key="d.id" class="machine-row" :class="{ on: on(d), dead: isDead(d), pending: !!store.pending[d.id] }"
              :disabled="isDead(d)" :aria-pressed="on(d)" @click="tap(d)">
        <Icon :name="iconFor(d)" :size="18" />
        <span class="machine-row-name">{{ featureName(d, device.name, room) }}</span>
        <span class="machine-row-state">{{ isDead(d) ? 'Not responding' : on(d) ? 'On' : 'Off' }}</span>
      </button>
    </div>
  </div>
</template>
