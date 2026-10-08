// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The house's own address, as the panel says it. design/address/ is the spec: asked once, as the last
 * and optional step of setup ("From outside, too?"), worded plainly -- the house is complete without
 * it, reaching it from outside is a service we run, the price in the open, and what stopping does --
 * and afterwards a row on This hub. Every rule a screen leans on is here, as a plain function, so
 * tests/address.test.ts can pin the picture the household chose.
 */
import type { AddressState, NameLook, Offer } from './api'

export const ZONE = 'elyir.app'

/** The setup step appears only when the service is offering and the house has no address yet. */
export const offersOutside = (a: AddressState | null | undefined) => !!a && a.offer.open && !a.house

/** What goes where the address becomes a house, from what somebody typed: Jordan's House -> jordans-house. */
export function cleanName(typed: string) {
  return typed.trim().toLowerCase().replace(/['’]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 30).replace(/-+$/, '')
}

/** The line beside the field. Nothing while it is being checked; one line in the color of the problem when it is not free, never a box. */
export function verdict(look: NameLook | null, typed: string): { tone: 'ok' | 'no' | ''; text: string } {
  const name = cleanName(typed)
  if (!name || !look || look.name !== name) return { tone: '', text: '' }
  if (look.free) return { tone: 'ok', text: `${look.address ?? `${name}.${ZONE}`} is free` }
  if (look.why === 'taken') return { tone: 'no', text: `${name}.${ZONE} is another house’s` }
  return { tone: 'no', text: look.why ?? 'That cannot be an address.' }
}

/** The price, split the way the board draws it: the amount large, the rest small. null when there is nothing to pay. */
export function price(offer: Offer): { amount: string; rest: string } | null {
  if (offer.by_hand || !offer.price) return null
  const [amount, ...rest] = offer.price.trim().split(/\s+/)
  return { amount, rest: rest.join(' ') }
}

/** The button that takes the address: paid on a phone, never on the shared wall -- or, by hand, simply taken. */
export const takeWords = (offer: Offer) => (offer.pay ? 'Continue on your phone' : 'Give it this address')

/** Where the phone pays, for the QR code: the payment page, told which house. */
export const payUrl = (offer: Offer, house: string) => offer.pay ? `${offer.pay}${offer.pay.includes('?') ? '&' : '?'}house=${encodeURIComponent(house)}` : null

// In UTC: an entitlement ends at midnight UTC on the day it was granted to, and reading it locally moved it a day early west of London.
const day = (ts: number) => new Date(ts * 1000).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' })

/** The row on This hub, once the house has an address: what it is, how it is, and the one thing to do. */
export function outsideRow(a: AddressState | null | undefined): { value: string; sub: string; action: 'Turn off' | 'Turn on' } | null {
  if (!a?.house || !a.address) return null
  const off = a.want === 'off'
  const value = off ? `${a.address} · off` : `${a.address} · on`
  let sub: string
  if (a.lost) sub = 'Our service no longer recognizes this house. Get in touch and we will put it back.'
  else if (off) sub = 'The web address is kept. Turn it on again whenever you like.'
  else if (a.waiting || (!a.on && a.carried)) sub = 'Getting the web address ready — about a minute.'
  else if (!a.carried) sub = a.offer.by_hand ? 'We are turning it on.' : 'Waiting for the payment to go through.'
  else sub = a.entitled_until ? `${a.offer.by_hand ? 'Free' : 'Paid up'} until ${day(a.entitled_until)}. If it ever stops, everything at home carries on as it is.` : 'On.'
  return { value, sub, action: off ? 'Turn on' : 'Turn off' }
}
