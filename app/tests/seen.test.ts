// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* When the house last saw a phone, as People says it (design/away/NamedC, the "seen" note). */
import { describe, expect, it } from 'vitest'
import { seen } from '../src/seen'

const NOW = 1_790_000_000
describe('seen', () => {
  it('says it the way the board does', () => {
    expect(seen(NOW - 30, NOW)).toBe('seen just now')
    expect(seen(NOW - 4 * 60, NOW)).toBe('seen just now')        // the brain writes last_seen every five minutes at most
    expect(seen(NOW - 2 * 3600 - 1, NOW)).toBe('seen 2 hours ago')
    expect(seen(NOW - 6 * 60, NOW)).toBe('seen 6 min ago')
    expect(seen(NOW - 3600, NOW)).toBe('seen 1 hour ago')
    expect(seen(NOW - 86400, NOW)).toBe('seen yesterday')
    expect(seen(NOW - 3 * 86400, NOW)).toBe('seen 3 days ago')
    expect(seen(null, NOW)).toBe('never seen')
  })
})
