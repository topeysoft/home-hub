// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A room's words, pinned to the sheet the household chose on 2 October (design/words-rooms/, C): a button
   says what the device says, and how a thing is says it like a person. So a device that cannot be reached
   has one name everywhere it is drawn, and the thermostat's tile and pane offer the same modes in the
   thermostat's own words. These fail on purpose if a tile or a pane grows a word of its own again. */
import { readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const src = (p: string) => readFileSync(`src/${p}`, 'utf8')
const room = ['readings.ts', 'pane.ts', 'Viewer.vue', ...readdirSync('src/tiles').map(f => `tiles/${f}`), ...readdirSync('src/panes').map(f => `panes/${f}`)]
const quoted = (s: string) => [...s.matchAll(/'([^'\n]*)'/g)].map(m => m[1])

describe('how a thing is', () => {
  it('has one name for a device that cannot be reached', () => {
    for (const f of room) for (const w of quoted(src(f)))
      expect(['Not responding', 'Offline', 'Not reachable', 'Unavailable'], `${f} says "${w}"`).not.toContain(w)
  })
  it('never says idle or docked, which are the device talking', () => {
    for (const f of room) for (const w of quoted(src(f))) expect(['Idle', 'Docked', 'Shut'], `${f} says "${w}"`).not.toContain(w)
  })
})

describe('the thermostat', () => {
  const modes = (f: string) => src(f).match(/const MODES: Record<string, string> = (\{[^}]*\})/)![1]
  it('offers the same modes on its tile and its pane, in its own words', () => {
    expect(modes('panes/ClimatePane.vue')).toBe(modes('tiles/ClimateTile.vue'))
    expect(modes('tiles/ClimateTile.vue')).toContain("heat: 'Heat'")
  })
  it('is set to a temperature, never asked for one', () => {
    for (const f of ['panes/ClimatePane.vue', 'tiles/ClimateTile.vue', 'pane.ts']) expect(src(f)).not.toMatch(/Asked for|ask for it/)
  })
})
