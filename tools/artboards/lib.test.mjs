// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The artboard viewer's arrangement, held to design/artboards/: A's contents and A's document, with
   C's canvas behind the Canvas switch, as chosen on 5 October 2026. The first test is the one that
   matters -- the viewer has to read its own collection the way the boards were decided -- and the
   rest pin the facts every page is drawn from: what was decided and which board won, which note
   argues which board, where a canvas opens, and what a search finds.

   node --test tools/artboards/lib.test.mjs */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { allCollections, byArea, decisionOf, documentOf, elsewhere, launchBoard, noteHeadFor, search, sentenceCase, pagesOf } from './lib.mjs'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import os from 'node:os'
import { contentsPage, documentPage, canvasPage } from './pages.mjs'

const DESIGN = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'design')
const page = (c, id) => pagesOf(c).find((p) => p.id === id)

/* a collection the way they are drawn: Today and three directions, one moved to a Not chosen page,
   a note under each board, a decision note on the left */
const drawn = () => ({
  pages: [{ id: 'q', name: 'The question' }, { id: 'q-rejected', name: 'The question: not chosen' }],
  artboards: [
    { file: 'Today.dc.html', x: 0, y: 0, w: 1440, h: 900, title: 'Today -- what ships', page: 'q' },
    { file: 'RowA.dc.html', x: 1560, y: 0, w: 1440, h: 900, title: 'A -- a row: volume is a fourth line', page: 'q' },
    { file: 'SwapB.dc.html', x: 3120, y: 0, w: 1440, h: 900, title: 'B -- swap', page: 'q' },
    { file: 'EdgeC.dc.html', x: 0, y: 0, w: 1440, h: 900, title: 'C -- edge', page: 'q-rejected' },
  ],
  annotations: [
    { id: 'decided', x: -620, y: -760, w: 500, page: 'q', text: 'DECIDED 1 OCTOBER 2026\n\nA with B’s swap. The row wins: nothing hidden.' },
    { id: 'why', x: -620, y: 0, w: 500, page: 'q', text: 'WHY THIS EXISTS\n\nBecause.' },
    { id: 'today', x: 0, y: 960, w: 680, page: 'q', text: 'TODAY -- DRAWN FROM THE SHIPPED PANEL\n\nAs it ships.' },
    { id: 'a', x: 1560, y: 960, w: 680, page: 'q', text: 'A -- A ROW: VOLUME IS A FOURTH LINE\n\nFOR: nothing hidden.\n\nAGAINST: one more line.' },
    { id: 'b', x: 3120, y: 960, w: 680, page: 'q', text: 'B -- SWAP\n\nThe corner turns.' },
    { id: 'c', x: 0, y: 960, w: 680, page: 'q-rejected', text: 'C -- EDGE\n\nA rail down the picture.' },
  ],
})

test('the viewer reads its own collection the way it was decided', async () => {
  const all = await allCollections(DESIGN)
  const me = all.find((c) => c.dir === 'artboards')
  assert.ok(me, 'design/artboards/ is a collection')
  assert.equal(me.name, 'The artboard viewer')
  assert.deepEqual(me.areas, ['Tools'])
  assert.equal(me.pages.find((p) => p.id === 'viewer').decision.chose, "A, with C's canvas")
  const doc = documentOf(me.canvas, 'viewer', 2026)
  assert.equal(doc.decision.board, 'ContentsA.dc.html', 'A won, and its front page is the board the viewer opens on')
  const [kept, lost] = doc.sections
  assert.deepEqual(kept.blocks.filter((b) => b.type === 'board').map((b) => b.board.file),
    ['Today.dc.html', 'ContentsA.dc.html', 'ReadA.dc.html', 'CanvasC.dc.html'], 'A, with C’s canvas kept beside it')
  assert.ok(lost.rejected)
  assert.deepEqual(lost.blocks.filter((b) => b.type === 'board').map((b) => b.board.file),
    ['LibraryB.dc.html', 'BoardB.dc.html', 'SpotlightC.dc.html'], 'B and C’s front page, kept with their cases')
  assert.ok(lost.blocks.every((b) => b.type !== 'board' || b.lost))
})

test('every collection in design/ has a name and an area of the house', async () => {
  for (const c of await allCollections(DESIGN)) {
    if (c.linked) continue // another repository's boards, linked in; they sort under Hardware
    assert.notEqual(c.areas[0], 'Not sorted yet', `design/${c.dir}/canvas.json needs "areas"`)
    assert.ok(c.name && c.name !== c.dir && c.name !== 'design/', `design/${c.dir} needs a "name" in canvas.json or an index.html`)
  }
})

test('no two collections are called the same', async () => {
  // design/bridge-light/ once copied its index.html from the strip controller's and kept its h1, so
  // the contents showed two "The strip controller on the wall" and a search for the bridge light
  // found neither.
  const seen = new Map()
  for (const c of await allCollections(DESIGN)) {
    assert.ok(!seen.has(c.name), `design/${c.dir} and design/${seen.get(c.name)} are both "${c.name}"`)
    seen.set(c.name, c.dir)
  }
})

test('a collection is found by its folder name', () => {
  const c = { dir: 'bridge-light', name: 'The strip controller on the wall', canvas: drawn(), date: '2026-10-05', pages: [] }
  c.pages = pagesOf(c.canvas).map((p) => ({ ...p, rejected: /not chosen/i.test(p.name), decision: null }))
  assert.ok(search([c], 'bridge light').groups.some((g) => g.dir === 'bridge-light'))
  assert.ok(search([c], 'bridge-light').groups.some((g) => g.dir === 'bridge-light'))
})

test('a decision is read from what collections already write', () => {
  const c = drawn()
  assert.deepEqual(decisionOf(page(c, 'q'), c, 2026),
    { on: '2026-10-01', chose: 'A with B’s swap', board: 'RowA.dc.html', source: 'note', note: 'decided', said: 'The row wins: nothing hidden.' })

  const head = drawn(); head.annotations[0].text = 'CHOSEN 2 OCTOBER 2026 -- B, WITH AN OPTIONAL ROOM\n\nThe room is optional.'
  assert.equal(decisionOf(page(head, 'q'), head, 2026).chose, 'B, with an optional room')
  assert.equal(decisionOf(page(head, 'q'), head, 2026).board, 'SwapB.dc.html')

  const own = drawn(); own.annotations.shift(); own.annotations[2].text = 'A -- ROW, CHOSEN 24 SEPTEMBER, WITH THE HEART DROPPED\n\nCheap.'
  assert.deepEqual([decisionOf(page(own, 'q'), own, 2026).chose, decisionOf(page(own, 'q'), own, 2026).on], ['A', '2026-09-24'])

  const titled = drawn(); titled.annotations.shift(); titled.artboards[2].title = 'B -- swap (chosen)'
  assert.equal(decisionOf(page(titled, 'q'), titled, 2026).board, 'SwapB.dc.html')

  // A page of losers beside it says something won, and nothing more.
  const guessed = drawn(); guessed.annotations.shift()
  assert.equal(decisionOf(page(guessed, 'q'), guessed, 2026).source, 'guessed')
  assert.equal(decisionOf(page(guessed, 'q'), guessed, 2026).board, null)

  // Said outright, it wins over everything else.
  const said = drawn(); said.pages[0].decided = { on: '2026-10-05', chose: 'B', board: 'SwapB.dc.html' }
  assert.equal(decisionOf(page(said, 'q'), said, 2026).board, 'SwapB.dc.html')

  const none = drawn(); none.annotations.shift(); none.pages.pop()
  assert.equal(decisionOf(page(none, 'q'), none, 2026), null)
})

test('a page reads in order, each board with the note under it, the losers folded in at the end', () => {
  const doc = documentOf(drawn(), 'q', 2026)
  const shape = doc.sections.map((s) => s.blocks.map((b) => b.type === 'board'
    ? `${b.board.file}${b.won ? '*' : ''}${b.lost ? '-' : ''}+${b.note?.id ?? ''}` : `(${b.note.id})`))
  assert.deepEqual(shape, [['(why)', 'Today.dc.html+today', 'RowA.dc.html*+a', 'SwapB.dc.html+b'], ['EdgeC.dc.html-+c']],
    'the decision note is the banner, so it is not also prose')

  // Where reading says the order, a note that follows a board is that board's.
  const read = drawn(); read.reading = ['why', 'Today.dc.html', 'today', 'RowA.dc.html', 'a', 'b', 'SwapB.dc.html']
  const blocks = documentOf(read, 'q', 2026).sections[0].blocks
  assert.deepEqual(blocks.map((b) => b.type === 'board' ? `${b.board.file}+${b.note?.id ?? ''}` : `(${b.note.id})`),
    ['(why)', 'Today.dc.html+today', 'RowA.dc.html+a', '(b)', 'SwapB.dc.html+', '(decided)'].filter((x) => x !== '(decided)'))
})

test('a canvas opens on the board that won', () => {
  assert.equal(launchBoard(drawn(), 'q', 2026).file, 'RowA.dc.html')
  const open = drawn(); open.annotations.shift(); open.pages.pop()
  assert.equal(launchBoard(open, 'q', 2026).file, null, 'nothing decided: fit everything, as before')
  open.launch = { file: 'SwapB.dc.html' }
  assert.equal(launchBoard(open, 'q', 2026).file, 'SwapB.dc.html')
})

test('search finds the phrase, the page it names, and folds the losers in with the page that beat them', () => {
  const c = { dir: 'player', name: 'What is playing', canvas: drawn(), date: '2026-10-01', pages: [] }
  c.pages = pagesOf(c.canvas).map((p) => ({ ...p, rejected: /not chosen/i.test(p.name), decision: /not chosen/i.test(p.name) ? null : decisionOf(p, c.canvas, 2026) }))
  const r = search([c], 'the question')
  assert.equal(r.groups.length, 1, 'one page, with its rejected sibling folded in')
  assert.deepEqual(r.groups[0].boards.map((b) => b.file), ['Today.dc.html', 'RowA.dc.html', 'SwapB.dc.html', 'EdgeC.dc.html'])
  assert.ok(r.groups[0].boards.find((b) => b.file === 'RowA.dc.html').won)
  assert.ok(r.groups[0].boards.find((b) => b.file === 'EdgeC.dc.html').lost)

  const n = search([c], 'nothing hidden')
  assert.deepEqual(n.groups[0].notes.map((x) => x.id), ['decided', 'a'], 'the decision comes first')
  assert.equal(n.groups[0].notes[1].text.slice(n.groups[0].notes[1].ranges[0][0], n.groups[0].notes[1].ranges[0][1]), 'nothing hidden')

  const loose = search([c], 'hidden row')
  assert.ok(loose.loose, 'no note has the phrase, so every word somewhere')
  assert.ok(loose.groups[0].notes.some((x) => x.id === 'decided'))
  assert.equal(search([c], 'x').groups.length, 0)
})

test('the contents group by area, newest first, with this viewer and hardware last', () => {
  const c = (dir, date, areas) => ({ dir, name: dir, date, areas })
  const groups = byArea([c('words-strip', '2026-10-02', ['Plain words', 'Light strips']), c('artboards', '2026-10-05', ['Tools']),
    c('roofline', '2026-10-01', ['Light strips']), c('wall', '2026-10-03', ['Hardware']), c('rooms', '2026-09-19', ['Wall screens'])]
    .sort((a, b) => b.date.localeCompare(a.date)))
  assert.deepEqual(groups.map((g) => g.area), ['Plain words', 'Light strips', 'Wall screens', 'Tools', 'Hardware'])
  assert.deepEqual(groups[1].list.map((x) => x.dir), ['words-strip', 'roofline'], 'a collection in two areas is under both')
})

test('the pages are drawn as the boards drew them', async () => {
  const all = await allCollections(DESIGN)
  const html = contentsPage(all)
  assert.match(html, /placeholder="Search \d+ boards and \d+ notes"/, 'ContentsA: one search field at the top')
  assert.equal((html.match(/data-theme-set=/g) || []).length, 3, 'Auto, Light and Dark')
  assert.equal((html.match(/class="card"/g) || []).length, 3, 'three lately, as pictures')
  assert.equal((html.match(/class="row"/g) || []).length, all.reduce((n, c) => n + c.areas.length, 0), 'every collection a line, under each of its areas')

  const cp = all.find((c) => c.dir === 'controller-panel')
  const doc = documentPage(cp, 'held', null, 2026)
  assert.match(doc, /class="decided"[\s\S]*Decided 1 Oct &mdash; A with B’s row\./, 'ReadA: the decision at the top, said once')
  assert.match(doc, /class="fold"/, 'the directions that lost, folded in at the end')
  assert.equal((doc.match(/<section class="bd"/g) || []).length, 6)
  assert.doesNotMatch(doc, /<h3>A — in the room: the light says it, where you reach for it<\/h3>/, 'a note beside its board does not repeat the title')

  const canvas = canvasPage(cp, 'held', null, 2026)
  assert.match(canvas, /let selected = "InRoomA\.dc\.html"/, 'CanvasC: it opens on the board that won')
  assert.match(canvas, /1 of 3/, 'and counts the pages that hold directions')
})

test('note headings are typed in capitals and read in sentence case', () => {
  assert.equal(sentenceCase('HELD DARK, AND WHY -- THE QUESTION'), 'Held dark, and why — the question')
  assert.equal(sentenceCase('DECIDED 1 OCTOBER 2026'), 'Decided 1 October 2026')
  assert.equal(sentenceCase("A WITH B'S ROW"), "A with B's row")
  assert.equal(sentenceCase('C, WITH A BADGE OF OUR OWN'), 'C, with a badge of our own')
  assert.equal(sentenceCase('C, FALLING BACK TO A'), 'C, falling back to A')
  assert.equal(sentenceCase('Already written this way'), 'Already written this way')
  assert.equal(noteHeadFor('A -- IN THE ROOM: THE LIGHT SAYS IT, WHERE YOU REACH FOR IT', 'A — in the room: the light says it where you reach for it'), '')
  assert.equal(noteHeadFor('TODAY -- DRAWN FROM THE SHIPPED PANEL', 'Today — the strip is dark, and the wall says it is on'), 'Drawn from the shipped panel')
  assert.equal(noteHeadFor('WHY THIS EXISTS', 'Today — what ships'), 'Why this exists')
})

/* From other checkouts, direction A of design/artboards/'s second page: a collection drawn in another
   worktree is on the front page before its branch is merged, and says Waiting for you until a page of
   it says what was picked. Built against a real repository with a real second worktree, because the
   whole point is what git says. */
test('a collection drawn in another checkout is found, and waits until it is picked', async () => {
  const tmp = mkdtempSync(path.join(os.tmpdir(), 'artboards-'))
  try {
    const repo = path.join(tmp, 'here'), there = path.join(tmp, 'there')
    const g = (cwd, ...a) => execFileSync('git', a, { cwd, stdio: 'pipe' }).toString()
    const put = (root, dir, canvas) => { mkdirSync(path.join(root, 'design', dir), { recursive: true }); writeFileSync(path.join(root, 'design', dir, 'canvas.json'), JSON.stringify(canvas)) }
    mkdirSync(repo)
    g(repo, 'init', '-q', '-b', 'development')
    g(repo, 'config', 'user.email', 't@e.st'); g(repo, 'config', 'user.name', 'Test')
    put(repo, 'rooms', { name: 'The Rooms tab', areas: ['Wall screens'], artboards: [{ file: 'Today.dc.html', x: 0, y: 0, w: 1440, h: 900, title: 'Today' }], annotations: [] })
    g(repo, 'add', '.'); g(repo, 'commit', '-qm', 'rooms')
    g(repo, 'worktree', 'add', '-q', '-b', 'puck-split-repos', there)
    // Fresh from the session: three directions, nothing picked, so no page of losers yet either.
    const light = drawn(); light.name = 'The bridge light'; light.areas = ['Light strips']; light.annotations.shift()
    light.pages.pop(); light.artboards = light.artboards.filter((b) => b.page === 'q'); light.annotations = light.annotations.filter((a) => a.page === 'q')
    put(there, 'bridge-light', light)
    g(there, 'add', '.'); g(there, 'commit', '-qm', 'Boards: the bridge light')
    put(there, 'rooms', { name: 'The Rooms tab', areas: ['Wall screens'], artboards: [{ file: 'Today.dc.html', x: 0, y: 0, w: 1440, h: 900, title: 'Today, again' }], annotations: [] })

    const design = path.join(repo, 'design')
    const here = await allCollections(design)
    let away = await elsewhere(design, here)
    const bridge = away.find((c) => c.dir === 'bridge-light')
    assert.ok(bridge, 'a new collection on another branch is found before it is merged')
    assert.deepEqual([bridge.kind, bridge.waiting, bridge.w, bridge.where.branch, bridge.where.ahead], ['new', true, 'there', 'puck-split-repos', 1])
    const rooms = away.find((c) => c.dir === 'rooms')
    assert.deepEqual([rooms.kind, rooms.waiting, rooms.uncommitted], ['changed', false, true], 'a change not committed yet counts, and is not waiting')
    assert.equal(away[0].dir, 'bridge-light', 'what waits comes first')

    const r = search([...here, ...away], 'bridge light')
    assert.equal(r.groups[0].dir, 'bridge-light', 'searching its name finds it first')
    assert.equal(r.groups[0].w, 'there')

    const html = contentsPage(here, '', away)
    assert.match(html, /From other checkouts/)
    assert.match(html, /Waiting for you/)
    assert.match(html, /href="\/read\?d=bridge-light&w=there"/)
    assert.doesNotMatch(contentsPage(here, '', []), /From other checkouts/, 'nothing elsewhere, no band')

    // Picked there: it stops waiting, and says what won in the same place.
    light.annotations.unshift({ id: 'decided', x: -620, y: -760, w: 500, page: 'q', text: 'DECIDED 5 OCTOBER 2026 -- A\n\nThe row.' })
    put(there, 'bridge-light', light)
    await new Promise((res) => setTimeout(res, 5))
    away = await elsewhere(design, here, { fresh: true })
    assert.equal(away.find((c) => c.dir === 'bridge-light').waiting, false)
  } finally { rmSync(tmp, { recursive: true, force: true }) }
})
