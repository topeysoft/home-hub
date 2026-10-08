// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Light or dark, which each screen picks for itself (design/appearance/, B, decided 7 October).
 *
 * Everything else about how the house looks is the house's answer and every screen shows it. This is
 * the one exception, because it is about the room the screen is in rather than about the house: a wall
 * in a bright kitchen and a phone in a dark bedroom want different answers at the same moment. So it is
 * kept in the screen's own browser and never sent to the hub, the way the Bench keeps a phone's.
 *
 * A phone-sized screen follows the phone's own setting until somebody says otherwise; a wall-sized one
 * stays dark, as every wall was before this existed, so no house's wall turns white overnight. The seam
 * is the panel's own (TOUCHED_AT in look.ts), the same one the resting screen keys on.
 */
import { ref } from 'vue'

export type Shade = 'light' | 'dark'
export type ShadeChoice = 'auto' | Shade

export const isShadeChoice = (v: unknown): v is ShadeChoice => v === 'auto' || v === 'light' || v === 'dark'

const KEY = 'shade'
const read = () => { try { return localStorage.getItem(KEY) } catch { return null } }

/** What this screen says when nobody has picked: a phone follows the phone, a wall stays dark. */
export const defaultChoice = (wide: boolean): ShadeChoice => (wide ? 'dark' : 'auto')

/** The shade a screen shows: a preview first (?shade=), then what was picked here, then the default. */
export function shadeOf(picked: unknown, wide: boolean, prefersDark: boolean, preview?: unknown): Shade {
  if (preview === 'light' || preview === 'dark') return preview
  const choice = isShadeChoice(picked) ? picked : defaultChoice(wide)
  return choice === 'auto' ? (prefersDark ? 'dark' : 'light') : choice
}

/** What this screen has picked, or null when it has not. Reactive, so the Look page and the shell agree. */
export const picked = ref<ShadeChoice | null>((() => { const v = read(); return isShadeChoice(v) ? v : null })())

export function pick(choice: ShadeChoice) {
  picked.value = choice
  try { localStorage.setItem(KEY, choice) } catch { /* a private window keeps nothing; the choice lasts the visit */ }
}

/** The shade the shell resolved, for the few drawings (the sky) that paint rather than inherit. */
export const shade = ref<Shade>('dark')
