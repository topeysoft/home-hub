// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Houses app: one app on the phone for every house it has joined (design/houses/). */
import { createApp } from 'vue'
import '@fontsource-variable/plus-jakarta-sans'
import './houses.css'
import App from './src/App.vue'

createApp(App).mount('#app')
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => { /* the app works without it */ })
