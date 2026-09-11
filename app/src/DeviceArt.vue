<script setup lang="ts">
/*
 * A device, drawn.
 *
 * Knows nothing about lamps: art.ts hands back a list of SVG elements and their
 * attributes and this paints them in order. All the drawing, and every number in
 * it, lives in art.ts where it can be tested without a browser -- which is how
 * the light pool that ran two pixels past its box got caught.
 *
 * Cropped into the corner rather than centred, because that is where it goes on
 * a real tile: the name and the state own the bottom left, and a device sitting
 * in the middle of a card is a catalogue photograph, not a room.
 */
import { computed } from 'vue'
import { BOX, device, materials, type ArtState, type Kind } from './art'
import { store } from './store'

const props = defineProps<{ kind: Kind; state: ArtState }>()

/* the same materials ArtDefs paints into the gradients, for the handful of marks
   that take a flat colour rather than one of them */
const art = computed(() => device(props.kind, props.state, materials(store.sky.elevation, store.sky.condition)))
</script>

<template>
  <svg class="tile-render" :viewBox="`0 0 ${BOX.w} ${BOX.h}`" aria-hidden="true" focusable="false" preserveAspectRatio="xMaxYMax meet">
    <component :is="m.el" v-for="(m, i) in art.marks" :key="i" v-bind="m.at" />
  </svg>
</template>
