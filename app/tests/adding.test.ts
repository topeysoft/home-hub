// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, beforeEach } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { SHOUTS_FOR, asThing, doors, kindOf, stripSheetOpen, stripWaiting, waitingBand } from '../src/adding'
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

/* THE TWO ROWS THAT COME BACK AFTERWARDS (design/strip/Later.dc.html). Both answers a strip gives at
   setup go stale -- it gets cut down, another is joined on, one is replaced by a different make -- and
   none of that should mean setting the thing up again. The board was drawn and chosen on 20 September
   and the row was never built, so a household whose strip measured wrong had no way to say so; that is
   exactly what came back from a real house on 21 September.

   What these hold is that it stays TWO rows and nothing more. The board's loudest argument is the one
   about what is absent: no effects, no segments, no zones. */
describe('asking a strip again, afterwards', () => {
  const pane = readFileSync('src/panes/LightPane.vue', 'utf8')

  it('offers both of the questions a strip is asked at setup, and only those', () => {
    expect(pane).toContain("askAgain('length')")
    expect(pane).toContain("askAgain('colors')")
    expect(pane.match(/askAgain\('/g) ?? []).toHaveLength(2)
  })

  it('says the length in metres, because that is how strips are bought', () => {
    expect(pane).toMatch(/\/ 60/)
    expect(pane).toContain('About ')
  })

  it('shows nothing at all on a light that is not a strip', () => {
    expect(pane).toContain('v-if="strip && !tuning"')
  })

  it('knows which strip it is by the house\'s own id and never by a model name', () => {
    expect(pane).toContain('r.device === props.device.hw')
    expect(pane.toLowerCase()).not.toContain('model ===')
  })

  it('adds no effects, segments or zones, which is the board\'s loudest argument', () => {
    // The strip-shaped part of the pane only: "effect" is ordinary English everywhere else in a file
    // about lighting, and a test that reads the whole file is a test about prose.
    const at = pane.indexOf('v-if="strip && !tuning"')
    const rows = pane.slice(at, pane.indexOf('rig-levels', at + 40))
    expect(rows.match(/<button/g) ?? []).toHaveLength(2)
    for (const no of ['effects', 'segment', 'zone', 'animation', 'preset'])
      expect(rows.toLowerCase()).not.toContain(no)
  })
})

/* WHEN AN ARRIVAL MAY TAKE A SCREEN. design/knock/, direction C with A, chosen 22 September.
   A household set several strips up in one evening and reported two things: the sheet takes the
   whole screen when a strip is powered on, which is not always a moment anybody asked to be
   interrupted in -- and it arrives up to a hundred and eight seconds late, which reads as the strip
   and the hub failing to talk to each other. They are one problem: an interruption nobody asked for
   has to be instant or it is a fault, and a passive advertiser cannot be heard instantly without
   scanning for ever. So it stopped being an interruption. */
describe('a knock does not take the screen', () => {
  it('leaves the house alone while a strip is only asking', () => {
    expect(stripSheetOpen('knocking', null)).toBe(false)
    expect(stripSheetOpen('press', null)).toBe(false)
    expect(stripSheetOpen('rhythm', null)).toBe(false)
  })

  it('opens when somebody taps the line in the band or the row on Add', () => {
    expect(stripSheetOpen('knocking', null, true)).toBe(true)
  })

  it('opens by itself where somebody is already asking, and only there', () => {
    expect(stripSheetOpen('knocking', 'add')).toBe(true)
    expect(stripSheetOpen('knocking', 'hub')).toBe(false)
    expect(stripSheetOpen('knocking', 'notes')).toBe(false)
  })

  it('lets it be put down again while still standing on Add', () => {
    /* Without this the page that opens the conversation opens it again the instant it is closed,
       and there is no way back to the list of everything else that is waiting. */
    expect(stripSheetOpen('knocking', 'add', false, true)).toBe(false)
  })

  it('and tapping the row asks again, which wins', () => {
    expect(stripSheetOpen('knocking', 'add', true, true)).toBe(true)
  })

  it('keeps the screen once it IS a conversation, wherever that began', () => {
    /* Past the asking the household is answering questions about a thing they are holding, and
       taking that away because they were not on Add would lose the conversation. */
    for (const beat of ['working', 'order', 'length', 'room', 'ready', 'failed'])
      expect(stripSheetOpen(beat, null), beat).toBe(true)
  })

  it('draws nothing at all when there is no strip', () => {
    expect(stripSheetOpen('none', 'add', true)).toBe(false)
    expect(stripSheetOpen(undefined, 'add', true)).toBe(false)
  })
})

/* AND WHAT THE BAND SAYS INSTEAD. A knock shouts for an hour and then folds in with whatever else
   is waiting, because a line that will not go away is the interruption again, slower -- and a strip
   knocks for forty-eight hours (docs/strip.md item 17). */
describe('the line in the band', () => {
  const now = 1_700_000_000_000
  const knock = (ago: number) => ({ state: 'knocking', since: (now - ago) / 1000 })
  const hue = { title: 'a Hue bridge' }

  it('says nothing when nothing is waiting', () => {
    expect(waitingBand([], null, now)).toEqual([])
    expect(waitingBand([], { state: 'ready' }, now)).toEqual([])
  })

  it('gives a fresh knock its own sentence, which opens the conversation', () => {
    expect(waitingBand([], knock(5 * 60 * 1000), now))
      .toEqual([{ id: 'knock', opens: 'strip', title: 'A light strip is here', sub: expect.any(String) }])
  })

  it('does not take the other line away while it shouts', () => {
    /* The first version returned one line, so a house with something on the network lost the line
       about it the moment a strip was plugged in. Found by opening the panel and looking. */
    const w = waitingBand([hue], knock(5 * 60 * 1000), now)
    expect(w.map(l => l.id)).toEqual(['knock', 'waiting'])
    expect(w[1].title).toBe('Found a Hue bridge')
  })

  it('stops shouting after an hour, and still says it is there', () => {
    expect(waitingBand([], knock(SHOUTS_FOR + 1), now))
      .toEqual([{ id: 'waiting', opens: 'add', title: '1 thing waiting to be set up', sub: 'a light strip' }])
  })

  it('folds in with everything else rather than staying a second line', () => {
    const w = waitingBand([hue], knock(SHOUTS_FOR + 1), now)
    expect(w).toHaveLength(1)
    expect(w[0]).toMatchObject({ title: '2 things waiting to be set up', sub: 'a Hue bridge, a light strip' })
  })

  it('shouts for a hub too old to say when the knocking started', () => {
    /* An unknown age would otherwise fold the instant it appeared, which is the one case where
       being wrong loses the sentence entirely. */
    expect(waitingBand([], { state: 'knocking' }, now)[0].id).toBe('knock')
  })

  it('leaves a house with nothing knocking exactly as it was', () => {
    /* The words for one thing found on the network are the panel's own and predate all of this. */
    expect(waitingBand([{ title: 'a Sonos speaker' }], null, now))
      .toEqual([{ id: 'waiting', opens: 'add', title: 'Found a Sonos speaker', sub: 'Tap to add it to the house.' }])
    expect(waitingBand([hue, { title: 'a Sonos speaker' }], null, now)[0].title)
      .toBe('Found 2 new things nearby')
  })
})
