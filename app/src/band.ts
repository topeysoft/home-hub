// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What the band shows on a phone, by kind (design/band/, chosen 2 October: B with C, line and chips).
 *
 * An ordinary week used to be four amber lines stacked under the tabs -- something stopped answering,
 * an update, two things found nearby, the passcode -- which on a phone is half of what is left of the
 * screen, and three of the four were not urgent. So every line in the band is one of three kinds:
 *
 *   needs  something is waiting on a person: it keeps a full line, with its reason, in amber
 *   news   something happened the person may want to see: a quiet chip in one row that sweeps sideways
 *   setup  something the house would like finished: it leaves Home for Finish setting up in This house
 *
 * The wall keeps its band as it was. It is already one row of chips at 1440, and the passcode line on
 * a wall is the screen everybody walks past, which is the point of it.
 *
 * Two lines are needs by earlier decisions and must stay so: a thing knocking keeps its own line for
 * its first hour (design/knock/), and Needs a look carries the only Sign in again there is (layout.ts).
 */
import { ref } from 'vue'
import { store } from './store'

export type BandItem =
  | 'ask' | 'notes' | 'knock' | 'controller' | 'updating' | 'signal'
  | 'update' | 'whats-new' | 'move' | 'waiting' | 'charging'
  | 'passcode' | 'location' | 'home-screen'
export type BandKind = 'needs' | 'news' | 'setup'

export const KIND: Record<BandItem, BandKind> = {
  ask: 'needs', notes: 'needs', knock: 'needs', controller: 'needs',
  // In progress, with a sentence that changes: a chip would cut the sentence, which is the news.
  updating: 'needs', signal: 'needs',
  update: 'news', 'whats-new': 'news', move: 'news', waiting: 'news', charging: 'news',
  passcode: 'setup', location: 'setup', 'home-screen': 'setup',
}

/* A phone, at the seam the rest of the panel uses for one (TOUCHED_AT in look.ts is the other side
   of it). Reactive, because a tablet turned on its side changes which side of it it is on. */
const query = typeof matchMedia === 'function' ? matchMedia('(max-width: 860px)') : null
export const narrow = ref(query?.matches ?? false)
query?.addEventListener?.('change', e => { narrow.value = e.matches })

/* Whether this page is running from the Home Screen rather than in a browser tab. */
export const standalone = typeof matchMedia === 'function'
  && (matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone === true)

/* The Home Screen suggestion, once somebody has said Done to it, stays done on this phone. */
const PHONE_DONE = 'phone-nudge'
export function homeScreenDismissed(): boolean { try { return localStorage.getItem(PHONE_DONE) === 'done' } catch { return false } }
export function dismissHomeScreen() { try { localStorage.setItem(PHONE_DONE, 'done') } catch {} }

export type SetupStep = { id: Extract<BandItem, 'passcode' | 'location' | 'home-screen'>; title: string; done: boolean }

/* Finish setting up, as This house shows it: every step that applies to this screen, done or not, so
   the count reads "2 of 3 done" rather than shrinking as it goes. The Home Screen step applies only to a
   phone, and is done once the house is on it or somebody said it is. The passcode is asked only once
   setup is done, as the band always did. */
export function setupSteps(s: { setupDone: boolean; locked: boolean; located: boolean; phone: boolean; onHomeScreen: boolean }): SetupStep[] {
  const steps: SetupStep[] = []
  if (s.setupDone) steps.push({ id: 'passcode', title: 'Set a passcode', done: s.locked })
  steps.push({ id: 'location', title: 'Where home is', done: s.located })
  if (s.phone) steps.push({ id: 'home-screen', title: 'Add to your Home Screen', done: s.onHomeScreen })
  return steps
}

export const setupLeft = (steps: SetupStep[]) => steps.filter(s => !s.done).length

/* The steps as they stand in this house, on this screen. Until the house has said whether it has a
   location, that step counts as done, so the list does not flash a step that was never missing. */
export function setupNow(): SetupStep[] {
  return setupSteps({
    setupDone: !!store.status?.setup_done,
    locked: store.status?.locked !== false,
    located: !store.ambientLoaded || !!store.ambient.location,
    phone: narrow.value,
    onHomeScreen: standalone || homeScreenDismissed() || store.homeScreenDone,
  })
}
