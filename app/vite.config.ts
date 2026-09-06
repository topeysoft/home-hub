import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const brain = 'http://localhost:8300'
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    proxy: {
      '/home': brain, '/devices': brain, '/rooms': brain, '/events': brain,
      '/stream': { target: brain.replace('http', 'ws'), ws: true },
    },
  },
})
