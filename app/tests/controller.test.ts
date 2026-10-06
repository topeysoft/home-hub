// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What a strip controller says about a light, and the roofline, as the wall draws them
   (design/controller-panel/ and design/roofline/, decided 1 October 2026). The words are the brain's;
   these pin where each one goes, and that the previews say exactly what the brain says. */
import { describe, expect, it } from 'vitest'
import type { Device, Room, Strip } from '../src/api'
import {
  HELD_PREVIEW, controllerBand, heldIn, heldLine, heldOf, nth, previewHeld, previewHeldNote, previewRoofline,
  previewStripBeat, previewStripRow, quietOf, roofCount, roofMeters, roofTile, yardSub,
} from '../src/controller'

const dev = (id: string, attrs: Record<string, any> = {}, state = 'on'): Device =>
  ({ id, name: 'Under-cabinet strip', room_id: 'kitchen', capability: 'light', state, attrs })

describe('a strip held dark', () => {
  it('is held only for the four reasons that keep it dark', () => {
    for (const r of ['supply', 'range', 'trips', 'wiring']) expect(heldOf(dev('k2', { strip: HELD_PREVIEW[r] }))?.held).toBe(r)
    expect(heldOf(dev('k2', { strip: HELD_PREVIEW.hot }))).toBeNull()
    expect(heldOf(dev('k2', { strip: HELD_PREVIEW.full }))).toBeNull()
    expect(heldOf(dev('k2'))).toBeNull()
  })

  it('running hot and holding under 5 A are one quiet line, and nothing on the tile', () => {
    expect(quietOf(dev('k2', { strip: HELD_PREVIEW.hot }))).toContain('The controller is warm')
    expect(quietOf(dev('k2', { strip: HELD_PREVIEW.full }))).toContain('Nothing needs doing')
  })

  it('says its reason under Staying off as a sentence (InRoomA)', () => {
    expect(heldLine(HELD_PREVIEW.supply)).toBe('It’s on a different power supply')
    expect(heldLine(HELD_PREVIEW.trips)).toBe('It kept cutting out')
  })

  it('the preview says exactly what the brain says (brain/hub/controller.py, pinned by tests/test_controller.py)', () => {
    expect(HELD_PREVIEW.supply.text).toBe('It was set up on a 12 V power supply, and it’s on a 24 V one now. A 12 V strip would burn on 24 V, so the controller is keeping it off.')
    expect(HELD_PREVIEW.supply.chip).toBe('The strip is staying off to protect itself')
    expect(HELD_PREVIEW.supply.next).toBe('Plug the 12 V supply back in')
  })

  it('a held preview darkens the strip and gives the room its chip; Needs a look its row and band line', () => {
    const room: Room = { id: 'kitchen', name: 'Kitchen', intent: 'unknown', devices: [dev('k1'), dev('k2', {}, 'on')] }
    previewHeld([room], 'supply')
    expect(heldIn(room)?.id).toBe('k2')
    expect(room.devices[1].state).toBe('off')
    const note = previewHeldNote('supply')!
    expect(note.band).toBe('The kitchen strip is staying off')
    expect(note.acts).toEqual([{ do: 'Show me', act: 'open', to: 'k2' }])
    expect(previewHeldNote('hot')).toBeNull()
  })
})

describe('the roofline', () => {
  const r = previewRoofline('christmas') as Extract<ReturnType<typeof previewRoofline>, { exists: true }>
  const roof = dev('roofline')

  it('is one light: on as one, with the occasion it shows', () => {
    expect(roofTile(roof, r)).toBe('On · Christmas')
    expect(roofTile({ ...roof, state: 'off' }, r)).toBe('Off')
  })

  it('a dark part is said by where it is, and the rest is still on (OneLight)', () => {
    expect(roofTile(roof, previewRoofline('dark'))).toBe('On · the garage end is dark')
  })

  it('counts its boxes and runs in words, and its length in lights', () => {
    expect(roofCount(r)).toBe('Three controllers, four strips')
    expect(roofMeters(412)).toBe('412 lights')
  })

  it('the yard names colors and orders, never numbers a box (TapA)', () => {
    const y = (previewRoofline('yard') as typeof r).yard!
    expect(y.rows.map(x => x.name)).toEqual(['Red', 'Blue', 'Green', 'Pink'])
    expect(nth(1)).toBe('1st'); expect(nth(2)).toBe('2nd'); expect(nth(3)).toBe('3rd'); expect(nth(4)).toBe('4th'); expect(nth(11)).toBe('11th')
    expect(yardSub(y, 0)).toBe('Its white light runs your way')
    expect(yardSub(y, 1)).toBe('Turned round — its white light ran toward you')
    expect(yardSub(y, 2)).toBe('Tap it if it comes next')
    expect(yardSub(y, 3)).toBe('Not yet')
  })
})

describe('the band, from a controller and the roofline', () => {
  it('a strip plugged in later is one line, and its tap asks the same question', () => {
    const s = { state: 'none', plugged: [{ id: 'c8', since: 1, text: 'Something new is plugged into the kitchen controller' }] } as Strip
    const [l] = controllerBand(s, null)
    expect(l.title).toBe('Something new is plugged into the kitchen controller')
    expect(l.strip).toBe('c8')
  })

  it('the roof coming on by itself is a line for an hour, and the line is the undo', () => {
    const now = Date.now()
    const r = { ...previewRoofline('christmas'), came_on: { at: now / 1000 - 60, text: 'The roofline came on at dusk' } }
    expect(controllerBand(null, r, now)[0].roof).toBe('roofline')
    expect(controllerBand(null, { ...r, came_on: { at: now / 1000 - 3700, text: 'x' } }, now)).toEqual([])
  })
})

describe('the setup beats a controller adds, previewed', () => {
  const base = { state: 'order' } as Strip
  it('each beat is the brain state the sheet draws', () => {
    expect(previewStripBeat('second', base)?.state).toBe('second')
    expect(previewStripBeat('second-red', base)).toMatchObject({ state: 'order', asking: 'red', run: 2 })
    expect(previewStripBeat('lit', base)).toMatchObject({ state: 'order', asking: 'lit' })
    expect(previewStripBeat('roofline', base)?.state).toBe('roofline')
    expect(previewStripBeat('evenings', base)?.state).toBe('evenings')
    expect(previewStripBeat('nope', base)).toBeNull()
  })
  it('a second strip on the row is its own length, and a light of its own names its light', () => {
    const row = { id: 's', online: true, count: 180, order: 'grb' }
    expect(previewStripRow(row, 'part')?.run2).toEqual({ count: 72, order: 'grb', own: false })
    expect(previewStripRow(row, 'own')?.light2).toBe('k2-toe')
    expect(previewStripRow(row, null)).toBe(row)
  })
})
