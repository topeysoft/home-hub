// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * When the house last saw a phone, as a phone row says it on People (design/away/, the note beside NamedC).
 *
 * Every new browser, profile or address a person opens the house in is a new phone, so a house collects rows
 * with the same name -- the maker's had five called Temi's screen -- and the one in use looked exactly like the
 * four left behind. When each was last seen is the one fact that tells them apart. The brain writes last_seen at
 * most every five minutes (hub/phones.py), so anything inside that is "just now".
 */
export function seen(lastSeen: number | null | undefined, now = Date.now() / 1000): string {
  if (!lastSeen) return 'never seen'
  const s = Math.max(0, now - lastSeen)
  if (s < 5 * 60) return 'seen just now'
  if (s < 3600) return `seen ${Math.floor(s / 60)} min ago`
  if (s < 86400) { const h = Math.floor(s / 3600); return `seen ${h} hour${h === 1 ? '' : 's'} ago` }
  const d = Math.floor(s / 86400)
  return d === 1 ? 'seen yesterday' : `seen ${d} days ago`
}
