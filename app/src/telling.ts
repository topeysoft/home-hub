// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Telling one new device from another.
 *
 * A thing arrives called whatever its driver called it -- "Switch 000a", "Wiz RGBW Tunable ABC123",
 * "Light 3" -- and New devices then asks which room it is in. Eleven of those in a list is a screen
 * nobody can answer honestly: the name says nothing, and picking a room becomes a guess to be undone
 * later from a room grid where the thing is now hiding among named ones.
 *
 * Two ways out, and this file is the quiet one. The house already knows more about a thing than the
 * name it is showing -- who made it, which model, what account brought it, whether it is on right now,
 * whether it is answering at all -- and none of that was on the screen. It is a line under the name.
 *
 * The loud one is in the row itself: blink it (api.identifyDevice) and go and look. This file says
 * which things can do that, so nothing offers a camera a button that cannot work.
 */
import type { Account, Device } from './api'
import { cap } from './store'
import type { UnitRow } from './units'

/** What a maker is called, without the part that belongs to a registrar. HA carries the legal name
    off the device registry -- "Signify Netherlands B.V.", "TP-Link Corporation Limited" -- and on a
    line meant to be read at a glance the suffix is noise in front of the word that matters. */
export function makerWord(maker?: string | null): string {
  const n = (maker ?? '').trim()
  if (!n) return ''
  return n.replace(/[,\s]*\b(b\.?v\.?|n\.?v\.?|inc\.?|llc|ltd\.?|limited|corp\.?|corporation|co\.?|gmbh|s\.?a\.?s?\.?|pty|plc|company|technolog(y|ies)|electronics)\b\.?/gi, '')
    .replace(/[\s,]+$/, '').trim() || n
}

/** What the house knows about this thing besides the name it came with: who it came from, and which
    model. Two things at most, because a third is a line nobody finishes reading.

    `accounts` is what /accounts returned, keyed by entry id, and it wins over the maker wherever there
    is one. "Philips Hue" is the box a person plugged in and signed into; the registry's own word for
    the maker of the same bulb is "Signify Netherlands B.V.", a name off a certificate that tells them
    nothing and pushes the model -- the half that actually differs between two rows -- off the end of
    the line. The maker is the answer where nobody signed into anything, which is what a radio brings.

    Nothing is said twice: a model that begins with who it came from ("Brilliant" / "Brilliant Smart
    Dimmer Switch") swallows it, and one that adds nothing at all is dropped instead. */
export function knownOf(d: Device, accounts: Record<string, Account> = {}): string[] {
  const who = (d.entry ? accounts[d.entry]?.kind : '') || makerWord(d.maker), model = (d.model ?? '').trim()
  if (!model) return who ? [who] : []
  if (!who || model.toLowerCase().startsWith(who.toLowerCase())) return [model]
  return who.toLowerCase().includes(model.toLowerCase()) ? [who] : [who, model]
}

/** How a thing stands right now, where that is worth saying on a screen about telling things apart.
    On is the useful one: a person can look up and see which lamp is lit, and that alone can answer the
    whole question. Not answering is the other, because it says in advance why blinking this one would
    show nobody anything. Everything else -- off, closed, idle -- is every other row on the screen too. */
export function nowOf(d: Device): { text: string; live: boolean } | null {
  if (d.state === 'unavailable') return { text: 'Not answering', live: false }
  return d.state === 'on' ? { text: 'On now', live: true } : null
}

/* ---------- the same, for a row ----------
   A row is a unit and may be two devices on one piece of hardware; the lead part is the one it is
   named after and the one that carries the hardware's maker, so the lead answers for the row. */
/** The quiet line under a name: "Philips Hue · Hue white A19". Empty where the house knows no more. */
export const known = (r: UnitRow, accounts: Record<string, Account> = {}) => knownOf(r.lead, accounts).join(' · ')
/** How this row stands, where that is worth a word of its own beside the line. */
export const nowWord = (r: UnitRow) => nowOf(r.lead)

/* What can be made to blink, and it is the brain's list (api.py, CAN_BLINK) said again here so the
   button is not offered and then refused. A camera cannot blink, a lock must not, and a blind takes
   half a minute to say anything. */
const BLINKS = ['light', 'switch', 'fan']
/** This row can be asked to show itself: something on it can act, and it is answering. */
export const canBlink = (r: UnitRow) =>
  BLINKS.includes(r.lead.capability.split('.')[0]) && r.lead.state !== 'unavailable'
/** The word for what it will do, so the button does not promise a light on a thing that has none. */
export const blinkWord = (r: UnitRow) => ({ light: 'Blink it', fan: 'Spin it' } as Record<string, string>)[cap(r.lead)] ?? 'Flash it'
