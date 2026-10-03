// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Houses app (design/houses/): its own small build, published to houses.elyir.app by tools/publish-houses.sh.
   Nothing is inlined into index.html -- the relay's policy runs no script it did not ship as a file. */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  root: fileURLToPath(new URL('./houses', import.meta.url)),
  publicDir: fileURLToPath(new URL('./houses/public', import.meta.url)),
  plugins: [vue()],
  build: {
    outDir: fileURLToPath(new URL('./dist-houses', import.meta.url)),
    emptyOutDir: true,
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
  server: { port: 5174, strictPort: true },
})
