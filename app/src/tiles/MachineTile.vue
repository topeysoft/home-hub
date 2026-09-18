<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * One machine, its features as rows: a fridge with its ice maker, its Ice Bites and its power cool
 * on one card rather than as three plugs in a row. machines.ts says which devices make a machine.
 *
 * Each row is its own switch and its own way in: a tap flips the feature, a hold opens it, and the
 * card itself is nothing but the frame around them -- it has no state of its own to be on or off,
 * because "the fridge is on" is not a thing anybody at a wall panel needs telling. A row that is on
 * wears the lamp color the way a lit tile does, so what is running reads from across the room.
 *
 * The card is a plain tile in the grid's eyes (`data-size`, the same body grid), so it packs the
 * column the way any other third or half does.
 */
import type { Device, Room } from '../api'
import { iconFor, isDead, perform, store } from '../store'
import { asDevice, featureName, type Machine } from '../machines'
import Icon from '../Icon.vue'

defineProps<{ machine: Machine; room?: Room | null }>()
const on = (d: Device) => d.state === 'on'
const word = (d: Device) => isDead(d) ? 'Not responding' : on(d) ? 'On' : 'Off'
function tap(d: Device) {
  if (isDead(d)) return
  perform(d, on(d) ? 'off' : 'on', undefined, { state: on(d) ? 'off' : 'on' })
}
</script>

<template>
  <!-- held anywhere but on a row, the card opens the machine's own page (the rows open their own); hold.ts
       keeps a press on a row for the row, so the two never fight -->
  <div class="tile plain machine" v-hold="() => (store.opened = asDevice(machine))">
    <!-- rung four of the artwork ladder, the same as any plug: no drawing of a fridge, so the glyph, oversized and faint, is the art -->
    <span class="tile-art" aria-hidden="true"><Icon name="appliance" :size="150" /></span>
    <div class="tile-body">
      <span class="tile-icon"><Icon name="appliance" /></span>
      <span class="tile-name">{{ machine.name }}</span>
      <div class="machine-rows" role="group" :aria-label="machine.name">
        <button v-for="d in machine.devices" :key="d.id" class="machine-row"
                :class="{ on: on(d), dead: isDead(d), pending: !!store.pending[d.id] }"
                :disabled="isDead(d)" :aria-pressed="on(d)" @click="tap(d)" v-hold="() => (store.opened = d)"
                :title="`Hold to open ${featureName(d, machine.name, room)}`">
          <Icon :name="iconFor(d)" :size="15" />
          <span class="machine-row-name">{{ featureName(d, machine.name, room) }}</span>
          <span class="machine-row-state">{{ word(d) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
