// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What stays on Home, and what never does (design/home-keep/, B, chosen 9 October 2026).
 *
 * Home is the house's row of what is on, and a household corrects it one thing at a time, from the
 * thing's own pane. Always keeps a thing on THIS screen even while it is off: the screen's answer,
 * kept on the screen like the wall's light or dark (shade.ts), because the hub cannot tell the wall
 * from a laptop on the same Wi-Fi. Never is the house's: the brain keeps it, and every screen leaves
 * the thing out (`off_home` on the device). Everything else is When it's on, which is the row as it
 * has always been, and what a house that never chooses keeps.
 */
import { ref } from 'vue'
import type { Device } from './api'

export type OnHome = 'always' | 'on' | 'never'

/* Four, so the row cannot turn back into a list somebody has to keep */
export const ALWAYS_MAX = 4
const KEY = 'home-always'

function read(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch { return [] }
}
const ids = ref<string[]>(read())

export const alwaysIds = () => ids.value
export const isAlways = (id: string) => ids.value.includes(id)

/** Where a thing stands. Never wins over Always: another screen may have set it since this one kept it. */
export function onHomeOf(d: Device): OnHome {
  return d.attrs?.off_home ? 'never' : isAlways(d.id) ? 'always' : 'on'
}

/** Keep it here, or let it go. A fifth is refused rather than pushing the oldest out: which one goes is the person's to say. */
export function keepAlways(id: string, yes: boolean): boolean {
  const now = ids.value.filter(x => x !== id)
  if (yes) {
    if (now.length >= ALWAYS_MAX) return false
    now.push(id)
  }
  ids.value = now
  try { localStorage.setItem(KEY, JSON.stringify(now)) } catch { /* a private window keeps nothing; the choice lasts the visit */ }
  return true
}

/* The doorbell and the thermostat are always on Home, a sensor never is, and an appliance's feature
   is on its own tile -- so none of them is offered the choice. */
const NOT_OFFERED = new Set(['sensor', 'motion', 'contact', 'camera', 'charger', 'climate', 'appliance'])
export const offersOnHome = (kind: string) => !NOT_OFFERED.has(kind)

/* The row in the pane, said the way the board says it: closed, where the thing stands; open, what the choice means here. */
export const ON_HOME_SAY: Record<OnHome, string> = { always: 'Always on Home', on: "On Home when it's on", never: 'Never on Home' }

const MORE = ['Nothing more', 'One more', 'Two more', 'Three more']
const inRoom = (name: string | null) => !name ? 'its room' : /['’]/.test(name) ? name : `the ${name}`
const listOf = (names: string[]) => names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`

/** The line under the chips. `full` names what already stays here, when Always was asked for a fifth. */
export function onHomeWhy(o: OnHome, room: string | null, full: string[] = []): string {
  if (full.length) return `${listOf(full)} already stay here. Set one of them to When it's on first.`
  if (o === 'never') return `Not on Home on any screen. It stays in ${inRoom(room)}.`
  if (o === 'always') return `Stays on this screen's Home, even when it's off. ${MORE[Math.max(0, ALWAYS_MAX - ids.value.length)]} can stay here.`
  return "Shows on Home while it's on, like everything else."
}

export type RowCard<P> =
  | { key: string; kind: 'device'; device: Device; always: boolean }
  | { key: string; kind: 'print'; printer: P }
  | { key: 'scenes'; kind: 'scenes' }

/**
 * The row, in the order drawn (design/nightfall/Main, then design/home-keep/KeepB): a print, then what
 * is playing, tall; the two glance cards in one column; what this screen keeps, in the order it was
 * kept; the first thing that is on; the scenes; the rest of what is on; the other glance cards.
 *
 * What is kept goes after the glance column and never in front of it, and a speaker that is kept and
 * playing stays the tall first card rather than being shown twice.
 */
export function homeRow<P extends { id: string }>(o: {
  prints: P[]; on: Device[]; lead: string | null; glance: Device[]; always: Device[]; scenes: boolean
}): RowCard<P>[] {
  const card = (d: Device, always = false): RowCard<P> => ({ key: d.id, kind: 'device', device: d, always })
  const playing = o.on.find(d => d.id === o.lead)
  const kept = o.always.filter(d => d.id !== playing?.id && !d.attrs?.off_home)
  const shown = new Set(kept.map(d => d.id))
  const tall = o.on.filter(d => d !== playing && !shown.has(d.id)).slice(0, 8)
  const out: RowCard<P>[] = o.prints.map(p => ({ key: `print:${p.id}`, kind: 'print', printer: p }))
  if (playing) out.push(card(playing, isAlways(playing.id)))
  out.push(...o.glance.slice(0, 2).map(d => card(d)))
  out.push(...kept.map(d => card(d, true)))
  out.push(...tall.slice(0, 1).map(d => card(d)))
  if (o.scenes) out.push({ key: 'scenes', kind: 'scenes' })
  out.push(...tall.slice(1).map(d => card(d)))
  out.push(...o.glance.slice(2).map(d => card(d)))
  return out
}
