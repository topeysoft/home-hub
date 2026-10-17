// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Where a 3D printer lives on the wall: design/printers/, chosen 2 October 2026 -- B, with an optional
   room. These pin the arrangement the boards drew, and they are meant to fail if it drifts: a print leads
   Your afternoon, a stopped printer with nothing printing is a line and not a card, the band never says
   what a card on the same screen already says, and a printing printer makes its room count as on. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { Device, Note, Printer, Room } from '../src/api'
import { applyPrinters, activity, done, forgetDone, keptPrints, roomActive, store, visibleRooms } from '../src/store'
import { rankRooms } from '../src/rooms'
import {
  actionLabel, asksTwice, bandNotes, cardLook, doneAt, finishedLine, hasCard, jobLine, layerLine, percent,
  printCards, printerChip, printerOn, span, swatch, timeLeft, wallActions, whoLine,
} from '../src/printers'

const job = { name: 'Phone stand', progress: 0.42, layer: 118, layers: 280, remaining_s: 5580, eta_clock: '4:20 pm',
              elapsed_s: 7440, colors: ['#f4f1ea'], material: 'PLA', filament: 'White PLA', thumbnail: '/printers/atlas/thumbnail' }
const printer = (id: string, state: Printer['state'], more: Partial<Printer> = {}): Printer => ({
  id, name: id[0].toUpperCase() + id.slice(1), connected: true, via: 'home', state, headline: 'x', detail: null,
  word: ({ ready: 'ready', printing: 'printing', needs_you: 'needs you', finished: 'done', problem: 'stopped', preparing: 'getting ready' } as any)[state ?? ''] ?? '',
  since: null, room: null, actions: [], temps: {}, camera: `/printers/${id}/camera`, job: null, ...more })

/* the boards' house: Atlas printing a phone stand, Juno stopped with nothing on its bed, Vega ready */
const atlas = (state: Printer['state'] = 'printing', more: Partial<Printer> = {}) => printer('atlas', state, { job: { ...job }, ...more })
const juno = () => printer('juno', 'problem', { headline: 'Juno stopped' })
const vega = (more: Partial<Printer> = {}) => printer('vega', 'ready', { headline: 'Ready', ...more })
const status = (printers: Printer[]) => ({ printers, found: [], asking: {}, asks: [] })

describe('a card for every print, not for every printer', () => {
  it('gives the print a card, and neither the stopped printer with nothing printing nor the ready one', () => {
    expect(printCards([vega(), atlas(), juno()]).map(p => p.id)).toEqual(['atlas'])
  })

  it('keeps the card while the print waits for somebody or is done, and lets a print stopped mid-way keep it in the fault color', () => {
    expect(['preparing', 'printing', 'needs_you', 'finished', 'problem'].every(s => hasCard(atlas(s as Printer['state'])))).toBe(true)
    expect(cardLook(atlas('needs_you'))).toBe('waiting')
    expect(cardLook(atlas('finished'))).toBe('done')
    expect(cardLook(atlas('problem'))).toBe('fault')
    expect(cardLook(atlas('preparing'))).toBe('printing')
  })

  it('puts the print that is waiting for somebody first, then printing, then done', () => {
    const cards = printCards([printer('a', 'finished', { job: { ...job } }), printer('b', 'printing', { job: { ...job } }), printer('c', 'needs_you', { job: { ...job } })])
    expect(cards.map(p => p.id)).toEqual(['c', 'b', 'a'])
  })
})

describe('the band never repeats a card on the same screen (StatesB)', () => {
  const note = (subject: string, kind: Note['kind'] = 'printer'): Note => ({ kind, subject, text: `${subject} needs you`, since: null })

  it('leaves out the line for a printer whose card is on the screen, and nothing else', () => {
    const notes = [note('atlas'), note('juno'), note('l1', 'offline')]
    const carded = printCards([atlas('needs_you'), juno()]).map(p => p.id)
    expect(bandNotes(notes, carded).map(n => n.subject)).toEqual(['juno', 'l1'])
  })

  it('still says a stopped printer with nothing printing, because it has no card to say it', () => {
    expect(bandNotes([note('juno')], printCards([juno()]).map(p => p.id))).toHaveLength(1)
  })
})

describe('the numbers, as a household says them', () => {
  const at = new Date(2026, 9, 2, 14, 47).getTime()

  it('says how far, how long, and when, the way the board does', () => {
    const p = atlas()
    expect(percent(p)).toBe(42)
    expect(layerLine(p)).toBe('Layer 118 of 280')
    expect(timeLeft(p)).toBe('1 h 33 min left')
    expect(doneAt(p, at, 'en-US')).toBe('4:20 PM')
    expect(whoLine(p)).toBe('Atlas · White PLA')
    expect(jobLine(p, at, 'en-US')).toBe('White PLA · started 12:43 PM')
    expect(swatch(p)).toBe('#f4f1ea')
  })

  it('says a span in hours and minutes, and never "0 min"', () => {
    expect(span(30)).toBe('under a minute')
    expect(span(12 * 60)).toBe('12 min')
    expect(span(2 * 3600)).toBe('2 h')
  })

  it('says when a print finished and how long it took', () => {
    const p = atlas('finished', { since: new Date(2026, 9, 2, 16, 18).getTime() / 1000, job: { ...job, elapsed_s: 13020 } })
    expect(finishedLine(p, 'en-US')).toBe('Finished 4:18 PM, after 3 h 37 min')
  })
})

describe('what the wall may do', () => {
  it('offers the printer’s own answers, in its own words, and asks twice only before stopping a print', () => {
    const p = atlas('printing', { actions: [{ id: 'pause', label: 'Pause' }, { id: 'cancel', label: 'Stop this print' }, { id: 'help', label: 'Show me what to check' }] })
    expect(wallActions(p).map(actionLabel)).toEqual(['Pause', 'Stop print'])
    expect(wallActions(p).filter(asksTwice).map(a => a.id)).toEqual(['cancel'])
    expect(actionLabel({ id: 'swap_slot', label: 'Use slot 6 instead' })).toBe('Use slot 6 instead')
  })
})

/* ---------- with a room chosen (WorkshopB, RankedB) ---------- */
const dev = (id: string, capability: string, state: string, room: string, attrs: Record<string, any> = {}): Device =>
  ({ id, name: id, room_id: room, capability, state, attrs })
const room = (id: string, name: string, devices: Device[]): Room => ({ id, name, devices, intent: 'unknown', set_by: null, hold_until: null })
const workshop = { id: 'workshop', name: 'Workshop' }
const house = () => [
  room('living', 'Living room', [dev('m1', 'media', 'playing', 'living', { media_title: 'The Bear' }), dev('l1', 'light', 'on', 'living', { brightness: 90 })]),
  room('kitchen', 'Kitchen', [dev('k1', 'light', 'on', 'kitchen', { brightness: 255 })]),
  room('workshop', 'Workshop', [dev('w1', 'light', 'off', 'workshop')]),
  room('garage', 'Garage', [dev('g1', 'cover', 'closed', 'garage')]),
  room('attic', 'Attic', []),
]

describe('a printer in a room', () => {
  beforeEach(() => { store.rooms = house() })
  afterEach(() => { store.printers = null; store.rooms = []; store.printsKept = {}; forgetDone(true) })

  it('counts printing as on, so the room ranks right behind the one with the television on', () => {
    store.printers = status([atlas('printing', { room: workshop }), vega({ room: workshop })])
    const ranked = rankRooms(store.rooms).map(r => r.id)
    expect(ranked.slice(0, 2)).toEqual(['living', 'workshop'])
    expect(roomActive(store.rooms[2])).toBe(true)
  })

  it('does not count a ready printer as on, and the room falls back to the quiet end', () => {
    store.printers = status([atlas('ready', { room: workshop, job: null }), vega({ room: workshop })])
    expect(roomActive(store.rooms[2])).toBe(false)
    expect(rankRooms(store.rooms).map(r => r.id).indexOf('workshop')).toBeGreaterThan(1)
  })

  it('names each printer in the room’s line, printing first, the way the board says it', () => {
    store.printers = status([vega({ room: workshop }), atlas('printing', { room: workshop })])
    store.rooms[2].devices[0].state = 'on'
    expect(activity(store.rooms[2])).toBe('Atlas printing · Vega ready · 1 light on')
    expect(printerChip(atlas())).toBe('Atlas printing, 42%')
  })

  it('makes a room with only a printer in it a room with something in it', () => {
    store.rooms = [store.rooms[4], ...store.rooms.slice(0, 4)]       // the attic first, where an empty room would not stay
    expect(visibleRooms().map(r => r.id).at(-1)).toBe('attic')
    store.printers = status([vega({ room: { id: 'attic', name: 'Attic' } })])
    expect(visibleRooms().map(r => r.id)[0]).toBe('attic')
    expect(activity(store.rooms[0])).toBe('Vega ready')
  })

  it('leaves a printer with no room out of every room', () => {
    store.printers = status([atlas()])
    expect(store.rooms.every(r => !activity(r).includes('Atlas'))).toBe(true)
    expect(printerOn(atlas())).toBe(true)
  })
})

describe('nothing vanishes under the finger', () => {
  afterEach(() => { store.printers = null; store.printsKept = {}; forgetDone(true) })

  it('keeps a done card in its place when the printer is ready again, until the panel looks away', () => {
    applyPrinters(status([atlas('finished')]))
    applyPrinters(status([atlas('ready', { job: null })]))
    expect(printCards(store.printers!.printers, keptPrints()).map(p => [p.id, p.state])).toEqual([['atlas', 'finished']])
    expect(done['printer:atlas']).toBeTruthy()
    forgetDone(true)
    expect(printCards(store.printers!.printers, keptPrints())).toEqual([])
  })

  it('lets a new print take the kept card’s place rather than standing beside it', () => {
    applyPrinters(status([atlas('finished')]))
    applyPrinters(status([atlas('ready', { job: null })]))
    applyPrinters(status([atlas('printing')]))
    expect(printCards(store.printers!.printers, keptPrints()).map(p => p.state)).toEqual(['printing'])
  })
})
