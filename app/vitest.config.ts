import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // store.ts reads location.search as it loads, the way the panel does in a browser.
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
    coverage: { provider: 'v8', include: ['src/**/*.ts'], exclude: ['src/main.ts'], reporter: ['text', 'json-summary'] },
  },
})
