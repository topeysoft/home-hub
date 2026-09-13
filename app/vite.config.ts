import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { proxyFor } from './dev-proxy.js'   // .js, not .ts: node16 resolution wants the emitted name

/* The dev server hands every path the brain owns to the brain: the real one on :8300, or the mock with
   `npm run dev:mock`, which starts both. Anything else is the panel itself, served by Vite with hot
   reload. Which paths those are lives in dev-proxy.ts, and a test holds it to what the panel calls. */
const brain = process.env.BRAIN || 'http://localhost:8300'
export default defineConfig({
  plugins: [vue()],
  server: { host: true, proxy: proxyFor(brain) },
})
