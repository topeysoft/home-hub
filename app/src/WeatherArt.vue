<script setup lang="ts">
/*
 * The sky, drawn.
 *
 * One illustration, assembled from the same numbers the sky canvas is painted
 * from, so the two can never disagree -- and a new condition needs no new
 * artwork. The numbers live in sky.ts beside the tables the canvas paints from;
 * this file only draws them. Night is not one of the conditions: the house
 * reports the weather and the sun says which light it is in, so the same fifteen
 * conditions each have to hold up twice. design/Weather.dc.html is that sheet,
 * in both lights.
 *
 * It lives apart from any one arrangement because two of them draw it: Rail puts
 * it in the corner beside a greeting, Wall gives it the left third of the screen.
 * How big it is and where it sits are the arrangement's business and are set in
 * CSS; everything about what it depicts is here.
 */
import { computed } from 'vue'
import { illustration } from './sky'
import { store } from './store'

const wx = computed(() => illustration(store.sky.elevation, store.sky.condition))
</script>

<template>
  <svg viewBox="0 0 210 150" aria-hidden="true">
    <defs>
      <radialGradient id="wxcloud" cx="34%" cy="28%" r="78%">
        <stop offset="0" :stop-color="wx.cloud.fill[0]" stop-opacity=".97" />
        <stop offset="62%" :stop-color="wx.cloud.fill[1]" stop-opacity=".93" />
        <stop offset="100%" :stop-color="wx.cloud.fill[2]" stop-opacity=".85" />
      </radialGradient>
      <!-- the bite only ever falls on the moon itself, and leaves the sky behind it alone -->
      <mask id="wxmoon" maskUnits="userSpaceOnUse" x="0" y="0" width="210" height="150">
        <rect x="0" y="0" width="210" height="150" fill="#fff" />
        <circle :cx="wx.moon.biteX" cy="38" r="27" fill="#000" />
      </mask>
    </defs>
    <path v-if="wx.stars.opacity > 0.02" :d="wx.stars.d" fill="#eef2fb" :opacity="wx.stars.opacity" />
    <circle cx="150" cy="44" r="27" :fill="wx.sun.col" :opacity="wx.sun.opacity" />
    <circle cx="150" cy="44" r="27" :fill="wx.moon.col" :opacity="wx.moon.opacity" mask="url(#wxmoon)" />
    <path v-if="wx.wind.d" :d="wx.wind.d" :stroke="wx.wind.col" stroke-width="3.4" stroke-linecap="round" fill="none" :opacity="wx.wind.opacity" />
    <g :transform="wx.cloud.transform" :opacity="wx.cloud.opacity" fill="url(#wxcloud)">
      <ellipse cx="72" cy="86" rx="56" ry="40" /><ellipse cx="118" cy="70" rx="48" ry="44" />
      <ellipse cx="150" cy="94" rx="42" ry="30" /><rect x="60" y="92" width="104" height="34" rx="17" />
    </g>
    <path v-if="wx.bolt.d" :d="wx.bolt.d" fill="#f3d18a" />
    <path v-if="wx.rain.d" :d="wx.rain.d" :stroke="wx.rain.col" stroke-width="4" stroke-linecap="round" fill="none" :opacity="wx.rain.opacity" />
    <path v-if="wx.snow.d" :d="wx.snow.d" :fill="wx.snow.col" :opacity="wx.snow.opacity" />
    <path v-if="wx.fog.d" :d="wx.fog.d" :stroke="wx.fog.col" stroke-width="6" stroke-linecap="round" fill="none" :opacity="wx.fog.opacity" />
  </svg>
</template>
