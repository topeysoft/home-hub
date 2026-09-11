import { defineConfig } from 'vitest/config'

/* One clock for every machine. Sunrise, sunset and "tomorrow" are all answers in the local zone, so
   a test written here and run on a CI box in UTC is testing a different thing. Chicago because that
   is where the mock house and the sun fixtures are. Set before any Date exists, or Node has already
   decided. */
process.env.TZ = 'America/Chicago'

export default defineConfig({
  test: {
    // store.ts reads location.search as it loads, the way the panel does in a browser.
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
    coverage: { provider: 'v8', include: ['src/**/*.ts'], exclude: ['src/main.ts'], reporter: ['text', 'json-summary'] },
  },
})
