<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getPhone, qrUrl } from './api'

/* Getting the house onto a phone. On the wall: a QR code for the panel's address and the steps for both kinds of phone.
   On the phone itself: the steps for this phone, since it is already here. The address is the one this screen was
   opened with when that is hub.local or a number, else hub.local; the brain's own address on the Wi‑Fi is offered as the
   fallback for a phone whose Wi‑Fi will not resolve .local names. */
defineProps<{ compact?: boolean }>()
const url = location.hostname.endsWith('.local') || /^\d+\.\d+\.\d+\.\d+$/.test(location.hostname) ? `${location.protocol}//${location.host}` : 'http://hub.local'
const ip = ref('')
onMounted(async () => {
  try { const p = await getPhone(); if (p.ip && !p.ip.startsWith('127.') && !url.includes(p.ip)) ip.value = p.ip } catch {}
})
/* The code is drawn by the hub. If it cannot be -- an old hub, or one whose
   drawing library was never installed -- the address is the whole answer anyway,
   so the card says that instead of leaving a broken picture on the wall. */
const code = ref(true)
const ua = navigator.userAgent
const os = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && 'ontouchend' in document) ? 'ios' : /Android/.test(ua) ? 'android' : 'other'
const onPhone = matchMedia('(max-width: 860px)').matches
const shown = computed<('ios' | 'android')[]>(() => onPhone ? [os === 'android' ? 'android' : 'ios'] : ['ios', 'android'])
const STEPS = {
  ios: { name: 'iPhone or iPad', steps: ['Open the address in Safari.', 'Tap the Share button, the square with an arrow pointing up.', 'Choose Add to Home Screen, then Add.'] },
  android: { name: 'Android', steps: ['Open the address in Chrome.', 'Tap the three dots at the top right.', 'Choose Add to Home screen, or Install app, then Add.'] },
}
</script>

<template>
  <div class="phone" :class="{ compact }">
    <div class="phone-qr" v-if="!onPhone && code"><img :src="qrUrl(url)" alt="A code the phone's camera opens the house from" width="132" height="132" @error="code = false" /></div>
    <div class="phone-text">
      <p class="phone-url">
        <template v-if="onPhone">You are at </template>
        <template v-else-if="code">Point the phone's camera at the code, or open </template>
        <template v-else>On the phone, open </template><b>{{ url }}</b>
        <span v-if="ip"> · if that does not open, type <b>http://{{ ip }}</b> instead</span>
      </p>
      <div class="phone-os" v-for="k in shown" :key="k">
        <span class="phone-os-name" v-if="!onPhone">{{ STEPS[k].name }}</span>
        <ol class="phone-steps"><li v-for="s in STEPS[k].steps" :key="s">{{ s }}</li></ol>
      </div>
      <p class="phone-foot">The house becomes an app on the phone: its own icon, full screen, no address to type. Same Wi‑Fi as the hub.</p>
    </div>
  </div>
</template>
