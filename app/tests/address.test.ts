// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The house's own address, as design/address/ chose it on 1 October 2026: asked once, as the optional
   last step of setup, worded plainly -- and only when the service is offering it, because an address
   nobody can pay for is a promise the house cannot keep. These fail on purpose if the words or the rule
   drift from the board (OfferPlain.dc.html, and Named.dc.html for the row on This hub). */
import { describe, expect, it } from 'vitest'
import type { AddressState, Offer } from '../src/api'
import { cleanName, offersOutside, outsideRow, payUrl, price, takeWords, verdict } from '../src/address'

const paid: Offer = { open: true, price: '$3 a month', pay: 'https://pay.example/start' }
const byHand: Offer = { open: true, price: null, pay: null, by_hand: true }
const closed: Offer = { open: false, price: null, pay: null }
const state = (over: Partial<AddressState> = {}): AddressState => ({ offer: paid, guess: 'temi', house: null, ...over })

describe('whether the step is offered at all', () => {
  it('appears only when the service is offering and the house has no address', () => {
    expect(offersOutside(state())).toBe(true)
    expect(offersOutside(state({ offer: closed }))).toBe(false)
    expect(offersOutside(state({ house: 'temi' }))).toBe(false)
    expect(offersOutside(null)).toBe(false)
  })
})

describe('the field', () => {
  it('turns what somebody typed into what an address can be', () => {
    expect(cleanName("Temi's House")).toBe('temis-house')
    expect(cleanName('  -The  Palace- ')).toBe('the-palace')
  })

  it('says free, or whose it is, in one line -- and nothing for an answer about a name nobody is typing now', () => {
    expect(verdict({ name: 'temi', free: true, address: 'temi.elyir.app' }, 'temi')).toEqual({ tone: 'ok', text: 'temi.elyir.app is free' })
    expect(verdict({ name: 'temi', free: false, why: 'taken', suggestions: [] }, 'temi')).toEqual({ tone: 'no', text: 'temi.elyir.app is another house’s' })
    expect(verdict({ name: 'api', free: false, why: 'That one is kept for the service itself.' }, 'api').text).toBe('That one is kept for the service itself.')
    expect(verdict({ name: 'tem', free: true }, 'temi')).toEqual({ tone: '', text: '' })
    expect(verdict(null, '')).toEqual({ tone: '', text: '' })
  })
})

describe('the offer, said plainly', () => {
  it('draws the amount large and the rest small, and draws nothing to pay by hand', () => {
    expect(price(paid)).toEqual({ amount: '$3', rest: 'a month' })
    expect(price(byHand)).toBeNull()
  })

  it('pays on a phone, never on the wall', () => {
    expect(takeWords(paid)).toBe('Continue on your phone')
    expect(takeWords(byHand)).toBe('Give it this address')
    expect(payUrl(paid, 'temi')).toBe('https://pay.example/start?house=temi')
    expect(payUrl({ ...paid, pay: 'https://pay.example/start?plan=a' }, 'temi')).toBe('https://pay.example/start?plan=a&house=temi')
    expect(payUrl(byHand, 'temi')).toBeNull()
  })
})

describe('the row on This hub', () => {
  it('is not there until the house has an address', () => {
    expect(outsideRow(state())).toBeNull()
  })

  it('says how it is, and offers the one thing to do', () => {
    const until = Date.UTC(2027, 9, 1) / 1000
    const carried = outsideRow(state({ house: 'temi', address: 'temi.elyir.app', want: 'on', on: true, carried: true, entitled_until: until }))!
    expect(carried.value).toBe('temi.elyir.app · on')
    expect(carried.sub).toMatch(/^Paid up until October 1, 2027\. If it ever stops, everything at home carries on as it is\.$/)
    expect(carried.action).toBe('Turn off')
    expect(outsideRow(state({ house: 'temi', address: 'temi.elyir.app', want: 'on', waiting: true }))!.sub).toBe('Getting the web address ready — about a minute.')
    expect(outsideRow(state({ house: 'temi', address: 'temi.elyir.app', want: 'on', carried: false }))!.sub).toBe('Waiting for the payment to go through.')
    expect(outsideRow(state({ offer: byHand, house: 'temi', address: 'temi.elyir.app', want: 'on', carried: false }))!.sub).toBe('We are turning it on.')
    const off = outsideRow(state({ house: 'temi', address: 'temi.elyir.app', want: 'off' }))!
    expect(off.value).toBe('temi.elyir.app · off'); expect(off.action).toBe('Turn on')
  })
})
