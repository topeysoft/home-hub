<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * A light strip, drawn.
 *
 * Not in art.ts for the same reason BridgeArt is not: everything in there is a small mark cropped
 * into the corner of a tile, and this is a whole object shown large in a sheet while somebody
 * decides something about it. The drawing is design/strip/ -- Fill, Order and Trim.
 *
 * It is drawn as PIXELS, at a pitch, because that is what the thing is: the one fact a household has
 * to hold about a strip is that it is made of separate lights in a row, and every question this sheet
 * asks follows from it. A smooth bar would be a lie about the object and would make "it fills one at
 * a time" read as a progress bar.
 *
 * WHAT IT EMITS DOES NOT TAKE THE AMBIENT. The colors here are fixed, the same rule BridgeArt keeps:
 * a thing's material relights with the shelf, the light it gives off does not.
 */
defineProps<{
  /* lit: on, in the house's warm. red: the color question. stripes: what a three-byte frame looks
     like on a strip that carries a separate white -- misaligned by a byte a pixel. fill: running,
     and it loops, because the panel cannot know how far along the real one is. dark: nothing. */
  show?: 'lit' | 'red' | 'green' | 'blue' | 'stripes' | 'fill' | 'dark'
}>()
</script>

<template>
  <div class="art" :class="show ?? 'lit'">
    <span class="glow"></span>
    <span class="track"></span>
    <span class="on"></span>
    <span class="head" v-if="show === 'fill'"></span>
  </div>
</template>

<style scoped>
.art { position: relative; width: 100%; height: 26px; }
.track, .on {
  position: absolute; inset: 0; border-radius: 4px;
  background: repeating-linear-gradient(90deg, rgba(255, 255, 255, .13) 0 4px, transparent 4px 7px);
}
.on { background: repeating-linear-gradient(90deg, var(--lamp) 0 4px, transparent 4px 7px); }
.glow {
  position: absolute; left: 0; right: 0; top: -62px; height: 150px; pointer-events: none;
  background: radial-gradient(42% 54% at 50% 50%, rgba(var(--lamp-rgb), .3), transparent 72%);
}
/* on, in the house's warm */
.lit .on, .fill .on { filter: drop-shadow(0 0 9px rgba(var(--lamp-rgb), .7)); }

/* the color question, and all three have to be drawable: a picker that offers "green" and paints it
   amber is a question nobody can answer. Saturated on purpose and NOT from the palette: --lamp and --danger are
   pastels chosen to read as ink on a dark screen, and a pastel on an emitter reads as white --
   which would make "is it red?" unanswerable. See AGENTS.md, emitter colors. */
.red .on { background: repeating-linear-gradient(90deg, #e2483e 0 4px, transparent 4px 7px);
           filter: drop-shadow(0 0 10px rgba(226, 72, 62, .8)); }
.red .glow { background: radial-gradient(42% 54% at 50% 50%, rgba(226, 72, 62, .3), transparent 72%); }

.green .on { background: repeating-linear-gradient(90deg, #4ac46a 0 4px, transparent 4px 7px);
             filter: drop-shadow(0 0 10px rgba(74, 196, 106, .75)); }
.green .glow { background: radial-gradient(42% 54% at 50% 50%, rgba(74, 196, 106, .26), transparent 72%); }
.blue .on { background: repeating-linear-gradient(90deg, #4b86e8 0 4px, transparent 4px 7px);
            filter: drop-shadow(0 0 10px rgba(75, 134, 232, .75)); }
.blue .glow { background: radial-gradient(42% 54% at 50% 50%, rgba(75, 134, 232, .26), transparent 72%); }

/* four channels' worth of data going into three, which is what the household actually sees */
.stripes .on {
  background: repeating-linear-gradient(90deg, #e2483e 0 4px, transparent 4px 7px, #4ac46a 7px 11px,
              transparent 11px 14px, #4b86e8 14px 18px, transparent 18px 21px);
}
.stripes .glow { background: radial-gradient(46% 54% at 50% 50%, rgba(120, 140, 190, .22), transparent 72%); }

.dark .on, .dark .glow { opacity: 0; }

/* IT LOOPS, AND IT IS AN ILLUSTRATION RATHER THAN A MIRROR. The panel cannot know how far along the
   real strip is -- that is the whole reason it is being asked -- so drawing a true position is not
   available and faking one would teach people to watch the screen. The thing to watch is the strip. */
.fill .on { animation: fill 5.5s linear infinite; }
.fill .head { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px;
              background: #fff6e6; box-shadow: 0 0 20px 5px rgba(var(--lamp-rgb), .85);
              animation: head 5.5s linear infinite; }
@keyframes fill { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
@keyframes head { from { left: 0; } to { left: calc(100% - 4px); } }
@media (prefers-reduced-motion: reduce) {
  .fill .on { animation: none; clip-path: inset(0 38% 0 0); }
  .fill .head { animation: none; left: 62%; }
}
</style>
