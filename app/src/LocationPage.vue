<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { store } from './store'
import LocationPicker from './LocationPicker.vue'

function close() { store.sheet = null }
</script>

<template>
  <div class="page">
    <p class="page-lede">The sky, sunrise and weather follow this. It stays on the hub and is never shared.</p>
    <LocationPicker @saved="close" />
  </div>
</template>
