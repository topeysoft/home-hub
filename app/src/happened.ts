// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The two decisions What happened makes for itself. Everything else on that page is words the brain
   wrote (brain/hub/happened.py) and this file must never second-guess them -- it picks a glyph and
   reports what a tap just did, and that is the whole of it. They live here rather than in the .vue
   for the reason why.ts does: a decision inside a template cannot be tested, and these two are the
   only places the panel could put the wrong face on a true sentence. */
import type { HappenedItem } from './api'

/* Which glyph. Driven by `word` -- what the thing was LEFT as -- and not by the device's kind,
   because the kind is not in the payload and asking the house for it would mean a row about a thing
   that has since been removed could not draw at all. */
export function iconFor(i: HappenedItem): string {
  if (i.kind === 'phone') return 'phone'
  if (i.word === 'unlocked') return 'lock'
  if (i.word === 'open') return 'home'
  return 'light'
}

/* What the thing will read as once the act lands, so the drawing can move before the house has
   answered. The WORDS a quieted row says are not here -- that is the store's `done` map and
   doneLine(), shared with Home, so the two cannot disagree about a light they both show. This is
   only the state to guess, which perform() needs and the store does not know from the act alone. */
export function guessFor(arg: string | undefined): { state: string } {
  if (arg === 'lock') return { state: 'locked' }
  if (arg === 'close') return { state: 'closed' }
  return { state: 'off' }
}
