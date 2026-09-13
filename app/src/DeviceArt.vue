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

/* corner: cropped into the bottom right of a tile, where the name and state own
   the other half. slot: filling a box that exists to hold a picture -- the
   album-art square, which is rung one's home and so is rung two's as well.
   face: the device's own face alone, centred, for the one tile that is built
   around the thing it draws rather than beside it. */
const props = withDefaults(defineProps<{ kind: Kind; state: ArtState; fit?: 'corner' | 'slot' | 'face' }>(), { fit: 'corner' })

/* the same materials ArtDefs paints into the gradients, for the handful of marks
   that take a flat colour rather than one of them */
const art = computed(() => device(props.kind, props.state, materials(store.sky.elevation, store.sky.condition)))

/* A face crops to the box art.ts drew it in; asking for one where there is none
   falls back to the whole drawing rather than to an empty square. */
const f = computed(() => (props.fit === 'face' ? art.value.face : undefined))
const box = computed(() => (f.value ? `${f.value.x} ${f.value.y} ${f.value.w} ${f.value.h}` : `0 0 ${BOX.w} ${BOX.h}`))
const CLASS = { corner: 'tile-render', slot: 'slot-render', face: 'face-render' }
</script>

<template>
  <svg :class="CLASS[fit]" :viewBox="box" aria-hidden="true" focusable="false"
       :preserveAspectRatio="fit === 'corner' ? 'xMaxYMax meet' : 'xMidYMid meet'">
    <component :is="m.el" v-for="(m, i) in art.marks" :key="i" v-bind="m.at" />
  </svg>
</template>
