<script setup lang="ts">
/*
 * The one set of materials every device drawing paints with.
 *
 * Mounted once by the shell, because an SVG gradient is addressed by id across
 * the whole document: one copy per tile would be a dozen elements claiming the
 * same name, and the browser would quietly use whichever it saw first. One copy
 * also means the whole shelf relights together when the sky moves, which is the
 * point -- see the rule at the top of art.ts.
 */
import { computed } from 'vue'
import { materials, GLOW, LAMP, LIT } from './art'
import { store } from './store'

const m = computed(() => materials(store.sky.elevation, store.sky.condition))
</script>

<template>
  <!-- Out of flow, and it matters: .shell is a two-column grid, so an in-flow
       svg here becomes a grid item and pushes the navigation rail into the
       stage's column. It cannot be display:none either -- a gradient inside a
       hidden subtree is not reliably referenceable. -->
  <svg width="0" height="0" aria-hidden="true" focusable="false" class="art-defs"
       style="position: absolute; width: 0; height: 0; overflow: hidden;">
    <defs>
      <!-- a cylinder: dark edge, light centre, dark edge -->
      <linearGradient id="mMetal" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" :stop-color="m.metalLo" /><stop offset="45%" :stop-color="m.metalMid" /><stop offset="100%" :stop-color="m.metalLo" />
      </linearGradient>
      <!-- a flat face, lit from above left, like everything else here -->
      <linearGradient id="mPlate" x1="0" y1="0" x2="0.3" y2="1">
        <stop offset="0" :stop-color="m.metalMid" /><stop offset="100%" :stop-color="m.metalLo" />
      </linearGradient>
      <linearGradient id="mMatte" x1="0" y1="0" x2="0.25" y2="1">
        <stop offset="0" :stop-color="m.matteHi" /><stop offset="100%" :stop-color="m.matteLo" />
      </linearGradient>
      <linearGradient id="mShade" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" :stop-color="m.shadeHi" /><stop offset="100%" :stop-color="m.shadeLo" />
      </linearGradient>
      <linearGradient id="mDark" x1="0" y1="0" x2="0.4" y2="1">
        <stop offset="0" :stop-color="m.darkHi" /><stop offset="100%" :stop-color="m.darkLo" />
      </linearGradient>
      <!-- a dark panel with a sheen across it, so a screen is glass and not a hole -->
      <linearGradient id="mScreen" x1="0.1" y1="0" x2="0.9" y2="1">
        <stop offset="0" :stop-color="m.screenHi" /><stop offset="58%" :stop-color="m.screenLo" /><stop offset="100%" :stop-color="m.screenHi" />
      </linearGradient>
      <linearGradient id="mFabric" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" :stop-color="m.fabricLo" /><stop offset="42%" :stop-color="m.fabricHi" /><stop offset="100%" :stop-color="m.fabricLo" />
      </linearGradient>

      <!-- Emitted light, hard-coded on purpose: these four do NOT take the sky.
           A lamp is warm because it is a lamp, and a tile that stops looking
           warm has stopped meaning "on". -->
      <radialGradient id="mPool" cx="50%" cy="34%" r="64%">
        <stop offset="0" :stop-color="GLOW" stop-opacity=".62" /><stop offset="54%" :stop-color="LAMP" stop-opacity=".22" /><stop offset="100%" :stop-color="LAMP" stop-opacity="0" />
      </radialGradient>
      <linearGradient id="mCone" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" :stop-color="GLOW" stop-opacity=".46" /><stop offset="100%" :stop-color="LAMP" stop-opacity="0" />
      </linearGradient>
      <radialGradient id="mGlass" cx="38%" cy="32%" r="76%">
        <stop offset="0" :stop-color="LIT" stop-opacity=".95" /><stop offset="62%" :stop-color="GLOW" stop-opacity=".62" /><stop offset="100%" :stop-color="LAMP" stop-opacity=".22" />
      </radialGradient>
    </defs>
  </svg>
</template>
