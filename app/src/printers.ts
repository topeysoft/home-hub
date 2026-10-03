// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Where a 3D printer lives on the wall, as rules rather than as a component. design/printers/, chosen
 * 2 October 2026: B, with an optional room.
 *
 * A PRINT LEADS YOUR AFTERNOON, the way a show that is playing leads it. A card for every print, not for
 * every printer: one appears when a print starts and stays while it is printing, waiting for somebody, or
 * done, and goes when the printer is Ready again -- at a moment nobody is watching, through the same `done`
 * map every other card on Home keeps its place by. A printer that stopped with nothing on its bed is not a
 * card: it is a job, so it is the band's line and a row on Needs a look, which the brain already sends.
 *
 * A ROOM IS THE HOUSEHOLD'S CHOICE, never a setup question. A printer with one is a tile in it, and printing
 * counts as on for that room's place on Rooms; a ready one does not. A printer with none lives under This
 * house, Printers. The card above is the same either way.
 *
 * Everything here is a function of the brain's view and nothing else, so the arrangement can be pinned by
 * a test that fails if it drifts (app/tests/printers.test.ts). The words are the printer's own or the
 * brain's; what this file adds is the frame -- which card, in which state, in which order -- and the
 * numbers said as a household says them.
 */
import type { Note, Printer, PrinterAction } from './api'

/** The four looks a print card has (design/printers/StatesB). Getting ready is printing's frame. */
export type CardLook = 'printing' | 'waiting' | 'done' | 'fault'

/** Does this printer have a print, and so a card on Your afternoon? */
export function hasCard(p: Printer): boolean {
  if (!p.job) return false
  /* A printer that stopped MID-PRINT still has the print on its bed, and its card turns the fault color
     in place rather than leaving -- the board's note on R2D2. One with no job is a row on Needs a look. */
  return ['preparing', 'printing', 'needs_you', 'finished', 'problem'].includes(p.state ?? '')
}

export function cardLook(p: Printer): CardLook {
  return p.state === 'needs_you' ? 'waiting' : p.state === 'finished' ? 'done' : p.state === 'problem' ? 'fault' : 'printing'
}

/**
 * The prints that lead the row, in order. One that is waiting for somebody goes first, because the
 * question is the reason it is there; then the ones printing; then the ones done, which are drained and
 * only holding their place. Within a look, the brain's order (by name).
 */
export function printCards(printers: Printer[], kept: Printer[] = []): Printer[] {
  const rank: Record<CardLook, number> = { waiting: 0, fault: 1, printing: 2, done: 3 }
  const live = printers.filter(hasCard)
  const held = kept.filter(k => !live.some(p => p.id === k.id))
  return [...live, ...held].sort((a, b) => rank[cardLook(a)] - rank[cardLook(b)])
}

/** Printing counts as on for a room's place on Rooms (RankedB). Ready does not, and nor does done. */
export const printerOn = (p: Printer) => ['preparing', 'printing', 'needs_you'].includes(p.state ?? '')

/** The printers a household has put in this room. */
export const printersIn = (printers: Printer[], roomId: string) => printers.filter(p => p.room?.id === roomId)

/** "OBI1 printing", "C3PO ready" -- a printer as one part of a room's line. */
export const printerPart = (p: Printer) => `${p.name} ${p.word || ''}`.trim()

/** "OBI1 printing, 42%" -- the same with how far, for a chip or a card that has no bar of its own. */
export function printerChip(p: Printer): string {
  const pct = percent(p)
  return p.state === 'printing' && pct != null ? `${printerPart(p)}, ${pct}%` : printerPart(p)
}

/**
 * THE BAND DOES NOT REPEAT A CARD ON THE SAME SCREEN (the note on design/printers/StatesB). OBI1 waiting
 * for a spool is its card, with the printer's question and its two answers on it; the brain also files it
 * on Needs a look, which is right for the page and wrong for the band above that card -- the same sentence
 * twice, one of them with nothing to tap. So on a screen that is showing a printer's card, the band leaves
 * that printer's line out. Needs a look, as a page, still lists it.
 */
export function bandNotes(notes: Note[], carded: string[]): Note[] {
  return notes.filter(n => !(n.kind === 'printer' && n.subject && carded.includes(n.subject)))
}

/* ---------- numbers, as a household says them ---------- */

export const percent = (p: Printer): number | null =>
  p.job?.progress == null ? null : Math.round(Math.max(0, Math.min(1, p.job.progress)) * 100)

/** "1 h 33 min", "12 min", "under a minute". The house's own way of saying a span. */
export function span(seconds: number): string {
  if (seconds < 60) return 'under a minute'
  const m = Math.round(seconds / 60)
  const h = Math.floor(m / 60), rest = m % 60
  if (!h) return `${m} min`
  return rest ? `${h} h ${rest} min` : `${h} h`
}

const clock = (at: number, locale?: string) => new Date(at).toLocaleTimeString(locale, { hour: 'numeric', minute: '2-digit' })

/** When it will be done, as a time on the wall's own clock: "4:20 PM". The printer's own `eta_clock` is
    written for its screen ("4:20 pm"); the house writes times the way every other line on it does. */
export function doneAt(p: Printer, now = Date.now(), locale?: string): string {
  const s = p.job?.remaining_s
  if (s == null) return p.job?.eta_clock?.toUpperCase() ?? ''
  return clock(now + s * 1000, locale)
}

/** "1 h 33 min left" */
export const timeLeft = (p: Printer) => p.job?.remaining_s == null ? '' : `${span(p.job.remaining_s)} left`

/** "Layer 118 of 280" */
export const layerLine = (p: Printer) => p.job?.layer != null && p.job.layers ? `Layer ${p.job.layer} of ${p.job.layers}` : ''

/** "Finished 4:18 PM, after 3 h 37 min" -- a done card, drained, says when. */
export function finishedLine(p: Printer, locale?: string): string {
  if (!p.since) return ''
  const after = p.job?.elapsed_s ? `, after ${span(p.job.elapsed_s)}` : ''
  return `Finished ${clock(p.since * 1000, locale)}${after}`
}

/** "White PLA · started 12:43 PM" -- the job's row on the pane. */
export function jobLine(p: Printer, now = Date.now(), locale?: string): string {
  const started = p.job?.elapsed_s != null && p.state !== 'finished' ? `started ${clock(now - p.job.elapsed_s * 1000, locale)}` : ''
  return [p.job?.filament, started].filter(Boolean).join(' · ')
}

/** "OBI1 · White PLA" -- under the part's name on a card. */
export const whoLine = (p: Printer) => [p.name, p.job?.filament].filter(Boolean).join(' · ')

/** The color of the first filament, for the swatch beside the job. */
export function swatch(p: Printer): string | null {
  const c = p.job?.colors?.[0]
  const hex = typeof c === 'string' ? c : c?.color
  return hex && /^#?[0-9a-f]{6}$/i.test(hex) ? (hex.startsWith('#') ? hex : `#${hex}`) : null
}

/* ---------- what may be done from here ---------- */

/*
 * The printer's own answers, as it offers them, minus the one a wall cannot honor. "help" asks the
 * printer to show what to check, which it does on its own screen and nowhere else: from the wall it
 * would be a button that does nothing visible. The detail above the buttons already is what to check.
 */
export const wallActions = (p: Printer): PrinterAction[] => p.actions.filter(a => a.id !== 'help')

/** A print that has been stopped cannot be resumed, so Stop asks twice, the way removing a thing does. */
export const asksTwice = (a: PrinterAction) => a.id === 'cancel'

/** Pause and Stop print, the pane's two, said the way the board says them. Every other answer keeps the
    printer's own label: "Use slot 6 instead" is the printer's sentence, not ours. */
export function actionLabel(a: PrinterAction): string {
  if (a.id === 'cancel') return 'Stop print'
  if (a.id === 'pause') return 'Pause'
  return a.label
}

/* ---------- found on the Wi-Fi ---------- */

/** "OBI1, R2D2 and C3PO" */
export function names(list: string[]): string {
  return list.length <= 1 ? (list[0] ?? '') : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`
}
