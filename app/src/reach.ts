// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Whether what is done on this screen is reaching the hub (design/out-of-reach/, C, decided 9 October 2026).
 *
 * The live connection is not the answer. On 9 October a kitchen screen kept its connection open for three
 * hours while every new request failed -- its Wi-Fi had stopped finding the hub by name -- so the cards
 * stayed current, the corner said Connected, and every tap flipped a card and flipped it back. So the screen
 * asks for itself: a fresh request every half minute, the same kind a tap makes, and two misses in a row
 * say so along the foot of the screen. A tap that never reached the hub counts as a miss and asks again at
 * once, so the second light is not a surprise too.
 *
 * While it is out a tap guesses nothing (store.ts, perform), and a card whose change did not get through
 * says so itself: B's card under C's band.
 */
import { reactive } from 'vue'
import { apiUrl, withToken } from './door'

export const PROBE_EVERY = 30_000
export const MISSES = 2
const WAIT = 8_000

export const reach = reactive({
  misses: 0,
  since: null as number | null,                   // the first miss of this run
  out: false,
  heard: null as number | null,                   // when the live connection last went, for "Last heard from it at"
  unreached: {} as Record<string, number>,        // cards whose last change did not get through, and when
})

export function missed(now = Date.now()) {
  if (!reach.misses) reach.since = now
  reach.misses++
  if (reach.misses >= MISSES) reach.out = true
}

export function reached() {
  reach.misses = 0; reach.since = null; reach.out = false
  for (const id of Object.keys(reach.unreached)) delete reach.unreached[id]
}

/** A tap that never reached the hub: the card keeps saying so, and the hub is asked again now. */
export function unreachedTap(id: string, now = Date.now()) {
  reach.unreached[id] = now
  missed(now)
  if (!reach.out) void probe()
}

/* Any answer from the hub is an answer: a 404 from an older brain still came from it. A 5xx can be the
   relay standing in for a hub it cannot reach, so that is a miss. */
export async function probe(go: typeof fetch = (...a) => fetch(...a)) {
  try {
    const r = await go(apiUrl('/alive'), { cache: 'no-store', headers: withToken(new Headers()), signal: AbortSignal.timeout(WAIT) })
    if (r.status < 500) reached(); else missed()
  } catch { missed() }
}

let timer: number | undefined
export function watchReach() {
  clearInterval(timer)
  timer = window.setInterval(() => { if (document.visibilityState === 'visible') void probe() }, PROBE_EVERY)
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && reach.misses) void probe() })
  window.addEventListener('online', () => void probe())
}

export type Band = { title: string; body: string; hushed: boolean }

/**
 * What the foot of the screen says, or nothing. `lost` is the live connection gone too, so what is shown
 * may be old: the room is hushed and the time is when the hub was last heard. A phone says phone, and one
 * that uses the house only on the home Wi-Fi is told the likeliest fix (PhoneC).
 */
export function bandFor(o: { out: boolean; lost: boolean; since: number | null; heard: number | null; phone: boolean; anywhere: boolean; at: (t: number) => string }): Band | null {
  if (!o.out && !o.lost) return null
  const t = o.at((o.lost ? o.heard : o.since) ?? Date.now())
  if (o.phone) return {
    title: 'This phone can’t reach the hub',
    body: o.anywhere ? `Since ${t}. It keeps trying on its own.`
      : `Since ${t}. It uses the house on your home Wi‑Fi, so check that it’s connected. It keeps trying on its own.`,
    hushed: o.lost,
  }
  if (o.lost) return {
    title: 'This screen can’t reach the hub',
    body: `Last heard from it at ${t}, so what you see may have changed since. It keeps trying. The switches on the wall still work.`,
    hushed: true,
  }
  return {
    title: 'Changes made here aren’t reaching the hub',
    body: `Since ${t}. What you see is up to date, and this screen keeps trying. The switches on the wall still work.`,
    hushed: false,
  }
}

/** The corner's word: Connected only while both the live connection and fresh requests are getting through. */
export function linkWord(up: boolean, lost: boolean, out: boolean): { word: string; cls: string } {
  if (up && !out) return { word: 'Connected', cls: 'up' }
  if (out || lost) return { word: 'Can’t reach the hub', cls: 'out' }
  return { word: 'Reconnecting', cls: '' }
}

/** The line a card says while its change has not got through. */
export const stillLine = (on: boolean) => ({ said: on ? 'Still on' : 'Still off', why: 'Changes can’t get through. Use the switch.' })
