<script setup lang="ts">
/*
 * The bridge itself, drawn.
 *
 * Not in art.ts, deliberately: everything in there is a 150x130 mark cropped into
 * the corner of a tile, and this is a whole object shown large in a sheet while
 * somebody decides whether to let it in. It does take the house's materials, so
 * it relights with the shelf -- what a thing is MADE OF takes the ambient (see the
 * rule at the top of art.ts); the light it EMITS does not, which is why the three
 * pools below are fixed colours and not mixed with the sky.
 *
 * The drawing is design/puck/Knock.dc.html and design/puck/Cable.dc.html.
 */
defineProps<{
  /* what its one light is saying. Blinking is the firmware's word for "still looking"; the panel
     only ever shows the colour, because a screen cannot be trusted to blink in step with a thing
     across the room. */
  light?: 'amber' | 'green' | 'red' | 'off'
  /* alone: the bridge on its own, the size of a decision. cable: it and the hub, with the lead
     between them -- the picture IS the instruction on that one, so it is not decoration. */
  scene?: 'alone' | 'cable'
}>()
</script>

<template>
  <svg v-if="scene === 'cable'" class="bridge-art" viewBox="0 0 504 208" fill="none" aria-hidden="true">
    <defs>
      <radialGradient id="bPool" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#f6dcae" stop-opacity=".85" /><stop offset="55%" stop-color="#e9b872" stop-opacity=".26" /><stop offset="100%" stop-color="#e9b872" stop-opacity="0" />
      </radialGradient>
    </defs>
    <rect x="92" y="30" width="9" height="30" rx="2.5" fill="url(#mMetal)" />
    <rect x="118" y="30" width="9" height="30" rx="2.5" fill="url(#mMetal)" />
    <rect x="60" y="56" width="98" height="104" rx="26" fill="url(#mDark)" />
    <rect x="60.8" y="56.8" width="96.4" height="102.4" rx="25.2" stroke="rgba(255,255,255,.16)" stroke-width="1.5" />
    <circle cx="109" cy="104" r="34" fill="url(#bPool)" />
    <circle cx="109" cy="104" r="6.5" fill="#f8e6c4" />
    <!-- the lead: one curve, the way anything flexible is drawn here -->
    <path d="M158 108 C 206 108, 214 150, 262 150 C 310 150, 316 104, 344 104" stroke="rgba(255,255,255,.22)" stroke-width="7" stroke-linecap="round" />
    <rect x="152" y="98" width="16" height="20" rx="4" fill="url(#mMetal)" />
    <rect x="336" y="94" width="16" height="20" rx="4" fill="url(#mMetal)" />
    <rect x="352" y="62" width="112" height="92" rx="20" fill="url(#mDark)" />
    <rect x="352.8" y="62.8" width="110.4" height="90.4" rx="19.2" stroke="rgba(255,255,255,.12)" stroke-width="1.5" />
    <circle cx="408" cy="108" r="4" fill="var(--live)" />
    <ellipse cx="408" cy="156" rx="64" ry="9" fill="rgba(0,0,0,.34)" />
  </svg>

  <svg v-else class="bridge-art" viewBox="0 0 160 190" fill="none" aria-hidden="true">
    <defs>
      <radialGradient id="bAmber" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#f6dcae" stop-opacity=".9" /><stop offset="55%" stop-color="#e9b872" stop-opacity=".3" /><stop offset="100%" stop-color="#e9b872" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="bGreen" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#bdf0d4" stop-opacity=".9" /><stop offset="55%" stop-color="#74c69d" stop-opacity=".3" /><stop offset="100%" stop-color="#74c69d" stop-opacity="0" />
      </radialGradient>
      <radialGradient id="bRed" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#f3bcbc" stop-opacity=".62" /><stop offset="55%" stop-color="#e08a8a" stop-opacity=".18" /><stop offset="100%" stop-color="#e08a8a" stop-opacity="0" />
      </radialGradient>
    </defs>
    <rect x="57" y="4" width="10" height="36" rx="2.5" fill="url(#mMetal)" />
    <rect x="93" y="4" width="10" height="36" rx="2.5" fill="url(#mMetal)" />
    <rect x="22" y="36" width="116" height="124" rx="31" fill="url(#mDark)" />
    <rect x="22.8" y="36.8" width="114.4" height="122.4" rx="30.2" stroke="rgba(255,255,255,.16)" stroke-width="1.5" />
    <template v-if="light !== 'off'">
      <circle cx="80" cy="98" :r="light === 'green' ? 46 : light === 'red' ? 30 : 42"
              :fill="light === 'green' ? 'url(#bGreen)' : light === 'red' ? 'url(#bRed)' : 'url(#bAmber)'" />
      <circle cx="80" cy="98" r="8" :fill="light === 'green' ? '#d7f7e5' : light === 'red' ? '#e8b3b3' : '#f8e6c4'" />
    </template>
    <circle v-else cx="80" cy="98" r="8" fill="rgba(255,255,255,.12)" />
  </svg>
</template>
