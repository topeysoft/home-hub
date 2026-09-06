import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/* The dev server hands every API path to the brain: the real one on :8300, or `BRAIN=http://localhost:8399 npm run dev`
   for the mock in mock/brain.mjs. Anything else is the panel itself. */
const brain = process.env.BRAIN || 'http://localhost:8300'
const api = ['/home', '/devices', '/rooms', '/events', '/setup', '/ambient', '/scenes', '/rules', '/drafts', '/discovered', '/catalog', '/flows', '/credentials', '/pair', '/geo', '/location', '/assistant']
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    proxy: {
      ...Object.fromEntries(api.map(p => [p, brain])),
      '/stream': { target: brain.replace('http', 'ws'), ws: true },
    },
  },
})
