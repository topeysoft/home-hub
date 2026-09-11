import { defineConfig, devices } from '@playwright/test'

/* The panel, driven in a real browser against the mock brain — the same house every time, with the
   clock frozen by ?at=. These are behaviour tests, not pictures: they assert on what the panel does,
   so they can fail a build without anyone having to look at a screenshot. */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: process.env.BASE || 'http://localhost:8399',
    trace: 'retain-on-failure',
    // One clock and one language for every machine. The panel draws the sky from the browser's own
    // time and writes its times with toLocaleTimeString, so a CI box in UTC would be running a
    // different test from the one written here. Chicago is where the mock house is.
    timezoneId: 'America/Chicago',
    locale: 'en-US',
  },
  /* Two screens, and a spec belongs to one of them: *.touch.spec.ts is the wall panel being used
     with a finger, everything else is a mouse on a 1280x800 wall. */
  projects: [
    { name: 'wall', testIgnore: /.*\.touch\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
    // Chromium, not the iPad's own WebKit: the touch specs dispatch through CDP, which only Chromium has.
    { name: 'touch', testMatch: /.*\.touch\.spec\.ts/, use: { ...devices['iPad Pro 11'], browserName: 'chromium', hasTouch: true } },
  ],
  // The mock serves ../dist, so the panel has to be built first; CI does that in the step before.
  webServer: {
    command: 'node mock/brain.mjs',
    url: 'http://localhost:8399/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
