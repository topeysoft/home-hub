// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Moving a phone to the house's own name, as design/away/ chose it (C): every phone moves once, the evening
 * the house gets its address, and letting one out is then only the switch on People. The rules a screen
 * leans on are here as plain functions, so tests/move.test.ts can pin them to the board.
 */
import type { Me, Phone } from './api'

/** The band line ("The house has its own address") is for a phone of the house that has not moved, opened
    anywhere but the address itself -- and never for the wall, which stays home and needs no door outside. */
export function offerMove(me: Me | null | undefined, origin: string): boolean {
  const p = me?.phone
  return !!me?.address && !!p && !p.moved && p.kind !== 'wall' && origin !== me.address
}

/** The one-time code a move arrives with: <address>/?move=<code>. */
export const moveCode = (search: string) => new URLSearchParams(search).get('move')

/** The same address, without the code in it, so a reload or a saved icon never carries a spent one. */
export function withoutCode(href: string): string {
  const u = new URL(href)
  u.searchParams.delete('move')
  return u.pathname + (u.search === '?' ? '' : u.search) + u.hash
}

/** Whether a phone row on People gets the Home only | Anywhere choice: a phone, not the wall; a house with an address;
    and only on a screen that keeps the house -- letting a phone out is the owner's to do. */
export const switchFor = (p: Phone, hasAddress: boolean, keys: boolean) => hasAddress && keys && p.kind !== 'wall'

/** The away screen waits, and opens by itself, only for a phone the house knows -- told so by the brain's own words. */
export const waitsToBeLetOut = (said: string | null | undefined) => !!said && said.startsWith('This phone works on your home')
