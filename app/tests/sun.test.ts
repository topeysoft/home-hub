/* Where the sun is. A port of brain/hub/sun.py, and the two must not drift apart:
   the panel paints dusk from this file and the brain fires after-dark routines from that one. */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { moonPhase, sunGuess, sunPosition } from '../src/sun'

// Vitest runs from app/, so the brain's copy of the table is one level up. Both suites read this same file.
const table = JSON.parse(readFileSync(resolve('../brain/tests/sun-positions.json'), 'utf8'))
const rows: { place: string; lat: number; lon: number; utc: string; elevation: number }[] = table.rows

describe('agreeing with the brain', () => {
  it('matches every position the brain computed, to a thousandth of a degree', () => {
    for (const r of rows) {
      const got = sunPosition(new Date(r.utc), r.lat, r.lon).elevation
      expect(got, `${r.place} at ${r.utc}`).toBeCloseTo(r.elevation, 3)
    }
  })
})

describe('the sun itself', () => {
  it('is up at midday and down at midnight', () => {
    expect(sunPosition(new Date('2026-09-11T17:00:00Z'), 41.88, -87.63).elevation).toBeGreaterThan(40)
    expect(sunPosition(new Date('2026-09-11T05:00:00Z'), 41.88, -87.63).elevation).toBeLessThan(-30)
  })

  it('stands higher in June than in December, and the other way round below the equator', () => {
    const june = (lat: number, lon: number) => sunPosition(new Date('2026-06-21T12:00:00Z'), lat, lon).elevation
    const december = (lat: number, lon: number) => sunPosition(new Date('2026-12-21T12:00:00Z'), lat, lon).elevation
    expect(june(51.51, -0.13)).toBeGreaterThan(december(51.51, -0.13))
    expect(june(-33.87, 151.21)).toBeLessThan(december(-33.87, 151.21))
  })

  it('never leaves the sky and always gives a compass bearing', () => {
    for (let h = 0; h < 24; h++) {
      const p = sunPosition(new Date(Date.UTC(2026, 5, 15, h)), 41.88, -87.63)
      expect(p.elevation).toBeGreaterThanOrEqual(-90)
      expect(p.elevation).toBeLessThanOrEqual(90)
      expect(p.azimuth).toBeGreaterThanOrEqual(0)
      expect(p.azimuth).toBeLessThan(360)
    }
  })
})

describe('without a location', () => {
  /* A hub nobody has told where it is still has to draw a sky that moves. */
  it('makes a day that rises, peaks around the middle and sets', () => {
    const at = (h: number, m = 0) => sunGuess(new Date(2026, 8, 11, h, m)).elevation
    expect(at(6, 45)).toBeCloseTo(0, 0)
    expect(at(13)).toBeGreaterThan(50)
    expect(at(19, 45)).toBeCloseTo(0, 0)
    expect(at(2)).toBeLessThan(0)
  })

  it('never jumps: the guess is continuous right around the clock', () => {
    let prev = sunGuess(new Date(2026, 8, 11, 0, 0)).elevation
    for (let m = 1; m < 1440; m++) {
      const e = sunGuess(new Date(2026, 8, 11, Math.floor(m / 60), m % 60)).elevation
      expect(Math.abs(e - prev), `a step at minute ${m}`).toBeLessThan(1)
      prev = e
    }
  })
})

describe('the moon', () => {
  it('runs from new through full and back inside one cycle', () => {
    expect(moonPhase(new Date(Date.UTC(2000, 0, 6, 18, 14)))).toBeCloseTo(0, 3)
    expect(moonPhase(new Date(Date.UTC(2000, 0, 21, 8, 0)))).toBeCloseTo(0.5, 1)
  })

  it('is always somewhere in the cycle, whatever date it is handed', () => {
    for (const d of ['1970-01-01', '1999-12-31', '2026-09-11', '2099-06-01']) {
      const p = moonPhase(new Date(d))
      expect(p, d).toBeGreaterThanOrEqual(0)
      expect(p, d).toBeLessThan(1)
    }
  })
})
