// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What the lights tell you, as the page arranges it (design/signal/Chosen.dc.html, Walked.dc.html).
 *
 * The house's own four come first, in the order the brain gives them; a household's own -- routines
 * that end in a signal -- come after, under their own label, because those are the answer to "and
 * anything else" and the four are the answer to the question the page is named for. Every row has the
 * same Try, and a try opens IN PLACE under its row: This house's page is no wider than 760px, so there
 * is no room beside the list, and a sheet over a sheet is a way to lose your place.
 *
 * Kept out of the component so the arrangement is a thing a test can hold (tests/signals.test.ts).
 */
import type { SignalsPage, SignalKind, StepState, Trying } from './api'
import { done } from './store'

export type Row = { key: string; name: string; kind: SignalKind; toward?: 'house' | 'out' | null; rgb: number[]; on: boolean; available: boolean; hint: string; own: boolean; rule?: string }

/** Every row the page draws, the four first. */
export function rowsOf(page: SignalsPage | null): { house: Row[]; own: Row[] } {
  if (!page) return { house: [], own: [] }
  return {
    house: page.meanings.map(m => ({ key: m.id, name: m.name, kind: m.kind, toward: m.toward, rgb: m.rgb, on: m.on, available: m.available, hint: m.hint ?? '', own: false })),
    own: page.own.map(r => ({ key: r.key, name: r.name, kind: r.kind, toward: r.toward, rgb: r.rgb, on: r.on, available: true, hint: '', own: true, rule: r.id })),
  }
}

/** Which drawing a row's preview is: a run is drawn going the way it will go. */
export function preview(kind: SignalKind, toward?: 'house' | 'out' | null): 'way' | 'back' | 'call' | 'fill' | 'end' {
  if (kind === 'way') return toward === 'out' ? 'back' : 'way'
  return kind
}

/** The emitter color as a CSS color, for the preview. Never a palette token: this is what the LED is sent. */
export const emitter = (rgb: number[]) => `rgb(${rgb.slice(0, 3).join(', ')})`

const clockOf = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).toLowerCase()

/** "Tried 8:14 pm · everything answered", while the panel is still looking; the done map decides how long. */
export function triedLine(key: string): string {
  const d = done[`signal:${key}`]
  return d ? `Tried ${clockOf(d.at)} · ${d.verb}` : ''
}
export const triedOk = (key: string) => done[`signal:${key}`]?.verb === 'everything answered'

/** The try this row is showing, if the latest one is about it. */
export function tryOf(page: SignalsPage | null, key: string): Trying | null {
  const t = page?.trying
  return t && t.of === key ? t : null
}

/** Strips a run or an end would have to guess the direction on, because nobody has said which end is the house. */
export function endsToAsk(page: SignalsPage | null, kind: SignalKind): string[] {
  if (!page || (kind !== 'way' && kind !== 'end')) return []
  return page.strips.filter(s => s.online && !s.house_end).map(s => s.id)
}

/** The line at the top of a try's report. */
export function headline(t: Trying, now = Date.now()): { title: string; sub: string } {
  if (t.state === 'running') return { title: 'Showing it now…', sub: '' }
  if (t.state === 'watching') {
    const left = Math.max(0, Math.ceil((t.ends * 1000 - now) / 60000))
    return { title: 'Watching for the real thing', sub: `${left === 1 ? '1 min' : `${left} min`} left · go and do it` }
  }
  if (t.state === 'passed') return { title: 'It worked, all the way through.', sub: '' }
  if (t.state === 'stopped') return { title: 'Stopped.', sub: '' }
  const decided = t.steps.find(s => s.key === 'decide')?.state === 'ok'
  return { title: decided ? 'A light did not answer.' : 'Nothing showed.', sub: '' }
}

/** One step's mark: a tick, a warning, a dash for "nothing to show", or an empty ring for "not reached". */
export const mark = (s: StepState) => ({ ok: '✓', no: '!', skip: '–', wait: '' })[s]

/** When a step happened, to the second: a chain is read by its order in time. */
export const stepTime = (at?: number) => at ? new Date(at * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }).replace(/\s?[ap]m$/i, '') : ''

/** This house's door: how many of the four are on, and how many of the household's own there are. */
export function doorHint(page: SignalsPage | null): string {
  if (!page) return 'Arriving, leaving, a door left open'
  const on = page.meanings.filter(m => m.on).length, own = page.own.length
  const four = on ? `${on} of ${page.meanings.length} on` : 'None on yet'
  return own ? `${four} · ${own} of your own` : four
}
