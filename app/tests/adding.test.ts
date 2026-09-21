// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, beforeEach } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { asThing, doors, kindOf, stripWaiting } from '../src/adding'
import { store } from '../src/store'

/* The vocabulary of adding, pinned. Five screens used to say the same thing five ways -- six words
   for leaving, four for starting -- and the whole redesign is that there is now one of each.
   A route that wants a word of its own is a route asking for a special case, and these fail it.
   design/adding/Words.dc.html. */

describe('the doors of beat one', () => {
  beforeEach(() => { store.status = { drivers: [] } as any; store.bridge = null })

  it('offers nothing about wires, only things a person can be holding', () => {
    expect(doors().map(d => d.title)).toEqual(['Something with its own app', 'A part of the house'])
  })

  it('opens the wall door only when a bridge can reach the walls', () => {
    store.bridge = { state: 'none', bridges: 1 } as any
    expect(doors().map(d => d.id)).toContain('wall')
  })

  it('opens the loose-things door for any radio, and never names one', () => {
    store.status = { drivers: [{ id: 'zwave', state: 'ready' }] } as any
    const thing = doors().find(d => d.id === 'thing')!
    expect(thing.title).toBe('A plug, bulb or sensor')
    expect(`${thing.title} ${thing.sub}`.toLowerCase()).not.toMatch(/zigbee|z.wave|matter|radio|mesh/)
  })
})

describe('what it turned out to be', () => {
  it('says it in objects, never in protocols', () => {
    expect(kindOf('dimmer')).toBe('a light that dims')
    expect(kindOf('plug')).toBe('a plug that switches')
  })
  it('admits it when the house does not know', () => {
    expect(kindOf('zwave_node')).toBe('something new')
    expect(kindOf(undefined)).toBe('something new')
  })
  it('turns the hub’s sentence back into a fragment', () => {
    expect(asThing('A light that dims, and a motion sensor.')).toBe('a light that dims, and a motion sensor')
    expect(asThing('One switch.')).toBe('one switch')
  })
  it('leaves a name alone', () => {
    expect(asThing('Sonos Roam')).toBe('Sonos Roam')
  })
  it('has nothing to say about nothing', () => {
    expect(asThing('')).toBeUndefined()
    expect(asThing(undefined)).toBeUndefined()
  })
})

describe('the word list', () => {
  const src = (p: string) => readFileSync(`src/${p}`, 'utf8')
  const pieces = readdirSync('src/prove').filter(f => f.endsWith('.vue'))
  /* The sheet a bridge knocks on is part of this vocabulary too. It is a different SURFACE -- an
     arrival opens itself, rather than being navigated to -- but an arrival that spoke its own
     language would put the whole exercise back where it started. */
  const everything = [src('Adding.vue'), src('BridgeSheet.vue'), ...pieces.map(f => src(`prove/${f}`))].join('\n')

  /* Every word that can end up on a button: the shell's own, and the ones the pieces ask for. */
  const ALLOWED = new Set([
    // the seven
    'Add', 'Have a look', 'That’s the one', 'Try again', 'Done', 'Add another', 'Not now',
    // questions only one beat can ask, in the same voice
    'Try the next one', 'No, none of them', 'Look again', 'I can reach the code',
    'It came with a QR code', 'No code on the back?', 'Continue', 'Add it',
    'Open their page', 'I’ve done that', 'Put them in rooms',
    'Copy',   // not a beat: it copies the address in the box beside it
    // the bridge's own two answers, which are answers and not ways out
    'Not mine', 'Leave it on', 'No, dark', 'Leave it here',
  ])

  it('never offers a word outside the list', () => {
    const asked = [...everything.matchAll(/label: '([^']+)'/g)].map(m => m[1])
    const drawn = [...everything.matchAll(/>([A-Z][^<>{}]{1,24})<\/button>/g)].map(m => m[1].trim())
    for (const w of [...asked, ...drawn]) expect(ALLOWED, `"${w}" is not one of the words`).toContain(w)
  })

  it('never brings back one of the six ways of leaving', () => {
    const gone = ['Cancel', 'Back', 'Stop', 'Later', 'OK', 'Open the door', 'Yes, add it', 'Yes, that is it']
    for (const w of gone) expect(everything).not.toContain(`label: '${w}'`)
    for (const w of gone) expect(everything).not.toContain(`>${w}</button>`)
  })

  it('keeps the button row in one place, which is not the pieces', () => {
    /* A piece says what it needs offering and the shell draws it. No piece owns an action row, and
       no piece draws the way out -- which is why leaving is the same word in the same corner on all
       of them, and why no route can quietly grow a "Cancel". */
    for (const f of pieces) {
      expect(src(`prove/${f}`), f).not.toContain('flow-actions')
      expect(src(`prove/${f}`), f).not.toContain('Not now')
    }
    expect(src('Adding.vue')).toContain('flow-actions')
  })
})

/* A KNOCKING STRIP HAS A PLACE ON THIS PAGE, and only one. Its own sheet covers the screen the
   moment one knocks, so the page is visible with a strip waiting only when a bridge has outranked
   it -- and then the household should still be told the strip is there. design/strip/Both.dc.html
   and Knock.dc.html: a strip is never started, it is plugged in and it knocks, so it belongs under
   "Already waiting" and never as a door somebody opens. */
describe('a light strip waiting its turn', () => {
  it('counts only the beats where it is still asking', () => {
    expect(stripWaiting('knocking')).toBe(true)
    expect(stripWaiting('press')).toBe(true)
    expect(stripWaiting('rhythm')).toBe(true)
  })

  it('is not waiting once it is a job, or over, or nothing', () => {
    for (const s of ['working', 'order', 'length', 'room', 'ready', 'failed', 'none', undefined])
      expect(stripWaiting(s)).toBe(false)
  })

  it('is never offered as a door, because nobody starts a strip', () => {
    store.status = { drivers: [{ id: 'matter', state: 'ready' }] } as any
    for (const d of doors()) expect(`${d.title} ${d.sub}`.toLowerCase()).not.toContain('strip')
  })
})

/* OUR OWN DOOR, ON THE WALL, PINNED TO THE BOARD IT WAS DRAWN FROM.
   design/door/PressIt.dc.html was chosen on 21 September and design/strip/Press.dc.html is the
   spec for the strip. What these hold is the composition, which is the part a screenshot of a
   passing test cannot: one thing to look at, one line saying nothing is happening yet, and exactly
   one button -- and it is the way DOWN a rung, not the way on. The beat cannot be finished from the
   wall at all, because the thing to press is not on the wall.

   And the rhythm below it, which shipped for a few hours as what everybody got and is now reached
   one way only. design/strip/ReachRhythm.dc.html. */
describe('the press, and the rung below it', () => {
  const sheet = readFileSync('src/StripSheet.vue', 'utf8')
  const beat = (name: string) => {
    const at = sheet.indexOf(`b.state === '${name}'`)
    expect(at, `no ${name} beat in StripSheet.vue`).toBeGreaterThan(-1)
    return sheet.slice(at, sheet.indexOf('<template v-else', at + 20))
  }

  it('asks for the press with nothing to read, count or type', () => {
    const press = beat('press')
    expect(press).toContain('Waiting for the press')
    expect(press).toMatch(/nothing to read, count or type/)
    expect(press).not.toMatch(/rhythm-count|input|field/)
  })

  it('offers one button, and it is the way down a rung rather than the way on', () => {
    const press = beat('press')
    const buttons = press.match(/<button/g) ?? []
    expect(buttons).toHaveLength(1)
    expect(press).toContain('It has no button I can reach')
    expect(press).toContain('@click="reach"')
    // No primary. A beat that cannot be finished from the wall must not draw something that looks
    // as though it could be.
    expect(press).not.toMatch(/class="button"/)
  })

  it('never names a code, a number or a label on our own door', () => {
    expect(beat('press').toLowerCase()).not.toMatch(/code|serial|label|number/)
  })

  it('keeps the four counts, one rung down, reached only from the press', () => {
    const rhythm = beat('rhythm')
    expect(rhythm).toContain('rhythm-count')
    expect(rhythm).toContain('It has started flashing')
    // The only door into it. If a second one ever appears, this is the line that says so.
    expect(sheet.match(/@click="reach"/g) ?? []).toHaveLength(1)
  })
})
