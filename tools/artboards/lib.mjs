// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// What the artboard viewer knows about design/, worked out from the files and nothing else.
//
// Every page the viewer draws -- the contents, a collection read as a document, a canvas, a search --
// is a different arrangement of the same few facts: what a collection is called and which part of the
// house it is about, when it last changed, what was decided on each of its pages and which board won,
// and which note argues which board. They are read from canvas.json and git on each request, so the
// viewer cannot drift from the canvases, and they are kept here, apart from any HTML, so that a test
// can hold them to the boards in design/artboards/ without a browser.
//
// A decision is said outright where somebody wrote it down ("decided" on a page in canvas.json) and is
// otherwise read from what collections already do: a note headed DECIDED or CHOSEN, a board titled
// "(chosen)", a page named "... not chosen" beside the one that won. A decision found the last way is
// marked as guessed, because it knows that something won and not what.
import { readFile, readdir, stat, lstat } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import path from 'node:path'

export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

// ---- words ------------------------------------------------------------------------------------

const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september',
  'october', 'november', 'december']
const KEEP = new Set(['I', 'OK', 'LED', 'LEDS', 'BLE', 'USB', 'UI', 'PCB', 'AGENTS.MD', 'HA', 'TV', 'API', 'URL', 'MQTT',
  'ESP32', 'WS2812', 'WS2815', 'RGB', 'RGBW', 'CCT', 'DNS', 'LAN', 'NFC', 'QR', 'PIN', 'POE', 'AC', 'DC'])

// Note headings are typed in capitals ("HELD DARK, AND WHY -- THE QUESTION") because the canvas draws
// them small and spaced. Read as a document they are set in sentence case; a single letter stays a
// capital because it is a direction (A, B, C), and so do months and the short names in KEEP.
export function sentenceCase(s) {
  const t = String(s).replace(/\s+--\s+/g, ' — ').trim()
  if (t !== t.toUpperCase()) return t
  let first = true
  return t.replace(/[A-Za-z][A-Za-z0-9.'’]*/g, (w, at) => {
    const bare = w.replace(/[.'’]+$/, '')
    // "WITH A BADGE" is an article; "A WITH B'S ROW" and "C, FALLING BACK TO A" are directions.
    const article = w === 'A' && !first && /^ (?!with\b|and\b|or\b|at\b|is\b|was\b|then\b|first\b|wins?\b)[A-Za-z]{2,}/i.test(t.slice(at + 1))
    let out
    if (article) out = 'a'
    else if (/^[A-F]['\u2019]S$/i.test(w)) out = w[0].toUpperCase() + w[1] + 's'
    else if (/\d/.test(w) || KEEP.has(bare.toUpperCase()) || (bare.length === 1 && !first)) out = w
    else if (MONTHS.includes(bare.toLowerCase())) out = w[0] + w.slice(1).toLowerCase()
    else out = w.toLowerCase()
    if (first) out = out[0].toUpperCase() + out.slice(1)
    first = false
    return out
  })
}

// "1 OCTOBER 2026", "24 September", "22 SEPTEMBER" -> "2026-10-01"; a missing year is the year given.
export function parseDate(s, year = new Date().getFullYear()) {
  const m = String(s).match(new RegExp(`\\b(\\d{1,2})\\s+(${MONTHS.join('|')})(?:,?\\s+(\\d{4}))?`, 'i'))
  if (!m) return null
  const mo = MONTHS.indexOf(m[2].toLowerCase()) + 1
  return `${m[3] || year}-${String(mo).padStart(2, '0')}-${m[1].padStart(2, '0')}`
}

const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const shortDate = (iso) => iso ? `${+iso.slice(8, 10)} ${SHORT[+iso.slice(5, 7) - 1]}` : ''

// A note is a heading, a blank line, and paragraphs.
export function splitNote(text) {
  const [head = '', ...body] = String(text ?? '').split(/\n\s*\n/)
  return { head: head.trim(), body: body.map((p) => p.trim()).filter(Boolean) }
}

// "A -- in the room: the light says it where you reach for it" -> "A — in the room". What the outline
// can fit: the part before a colon, or before the first comma, whichever comes first.
export function shortTitle(title) {
  const t = String(title ?? '').replace(/\s+--\s+/g, ' — ')
  const cut = t.search(/[:,(]/)
  return (cut > 0 ? t.slice(0, cut) : t).trim()
}

// The direction letter a title or a decision starts with: "A — in the room", "C, falling back to A".
const letterOf = (s) => (String(s ?? '').match(/^([A-F])(?=[\s,.—–-]|$)/) || [])[1] || null

// ---- one canvas -------------------------------------------------------------------------------

export const isRejected = (page) => /not chosen|unaccepted/i.test(page?.name || '')

// Every canvas has pages; one with none in its file has a single unnamed one.
export function pagesOf(canvas) {
  return canvas.pages?.length ? canvas.pages : [{ id: null, name: null }]
}

export function onPage(item, page, canvas) {
  const pages = pagesOf(canvas)
  if (pages.length === 1) return true
  return (item.page ?? pages[0].id) === page.id
}

// The page that holds the directions a rejected page was moved off: "Held dark, and why: not chosen"
// belongs to "Held dark, and why"; a page called just "Not chosen" belongs to the first page.
export function siblingOf(page, canvas) {
  const pages = pagesOf(canvas)
  const named = String(page.name || '').replace(/\s*[:—-]?\s*(not chosen|unaccepted.*)$/i, '').trim().toLowerCase()
  return pages.find((p) => !isRejected(p) && named && String(p.name || '').toLowerCase() === named)
    || pages.find((p) => !isRejected(p))
}

const DECIDED_HEAD = /^\s*(decided|chosen|picked|approved)\b/i

// What was decided on one page, and which board won. Returns null when nothing says so.
export function decisionOf(page, canvas, year) {
  const boards = (canvas.artboards || []).filter((b) => onPage(b, page, canvas))
  const notes = (canvas.annotations || []).filter((a) => onPage(a, page, canvas))
  const winnerFor = (chose, explicit) => {
    if (explicit) return explicit
    const l = letterOf(chose)
    const b = (l && boards.find((x) => letterOf(x.title) === l))
      || boards.find((x) => /^chosen\b/i.test(x.title || '') || /\(chosen/i.test(x.title || ''))
    return b?.file || null
  }
  const said = page.decided || (pagesOf(canvas).length === 1 && canvas.decided)
  if (said) return { on: said.on || null, chose: said.chose || null, board: winnerFor(said.chose, said.board), source: 'canvas', note: null }
  // A note headed DECIDED 1 OCTOBER 2026, or CHOSEN 2 OCTOBER 2026 -- B, WITH AN OPTIONAL ROOM.
  // The latest one wins: a page that was decided, then amended, says so twice.
  const decided = notes.filter((a) => DECIDED_HEAD.test(splitNote(a.text).head))
  if (decided.length) {
    const ranked = decided.map((a) => ({ a, on: parseDate(splitNote(a.text).head, year) }))
      .sort((p, q) => String(q.on).localeCompare(String(p.on)))
    const { a, on } = ranked[0]
    const { head, body } = splitNote(a.text)
    const after = head.split(/\s+(?:--|—)\s+/).slice(1).join(' — ')
    const first = (body[0] || '').split(/(?<=\.)\s/)[0]
    const chose = after ? sentenceCase(after) : first.replace(/\.$/, '').slice(0, 90)
    // What the note says after the decision itself, for a banner that should not say it twice.
    const said = (after ? body[0] || '' : (body[0] || '').slice(first.length)).trim()
    return { on, chose, board: winnerFor(chose), source: 'note', note: a.id ?? null, said }
  }
  // A -- ROW, CHOSEN 24 SEPTEMBER, WITH THE HEART DROPPED: a direction's own note saying it won.
  for (const a of notes) {
    const { head } = splitNote(a.text)
    if (letterOf(head) && /\bchosen\b/i.test(head) && !/not chosen/i.test(head)) {
      const l = letterOf(head)
      return { on: parseDate(head, year), chose: l, board: winnerFor(l), source: 'note', note: a.id ?? null }
    }
  }
  // C -- news once, a job when it repeats (chosen)
  const titled = boards.find((b) => /\(chosen/i.test(b.title || ''))
  if (titled) return { on: parseDate(titled.title, year), chose: letterOf(titled.title), board: titled.file, source: 'title', note: null }
  // A "not chosen" page beside this one: something here won, and nothing says what.
  if (!isRejected(page) && pagesOf(canvas).some((p) => isRejected(p) && siblingOf(p, canvas) === page)) {
    return { on: null, chose: null, board: null, source: 'guessed', note: null }
  }
  return null
}

// A note's heading often restates its board ("A -- IN THE ROOM: THE LIGHT SAYS IT..." under "A — in the
// room: the light says it..."). Beside the board that is said twice, so the heading loses the part the
// title already says, and goes altogether when nothing is left.
export function noteHeadFor(head, title) {
  const h = sentenceCase(head)
  if (!title) return h
  const words = (s) => new Set(String(s).toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').split(' ').filter((w) => w.length > 2))
  const strip = (s) => String(s).replace(/\s+--\s+/g, ' \u2014 ').replace(/^.{1,40}?\s+\u2014\s+/, '')
  const t = String(title).replace(/\s+--\s+/g, ' \u2014 ')
  const sameLead = t.split(' \u2014 ')[0].toLowerCase() === h.split(' \u2014 ')[0].toLowerCase() && h.includes(' \u2014 ')
  if (!sameLead) return h
  const rest = strip(h), a = words(rest), b = words(strip(t))
  const shared = [...a].filter((w) => b.has(w)).length
  if (!a.size || shared / a.size > 0.6) return ''
  return rest[0].toUpperCase() + rest.slice(1)
}

const lostTitle = (b) => /\(not chosen/i.test(b.title || '')

// ---- the document: a page of a collection, in reading order ----------------------------------
//
// A collection read as a document is one page at a time: its rejected sibling folded in at the end,
// each board with the note that argues it beside it, and the notes that argue no single board as
// prose between them. canvas.json's `reading` says the order where somebody wrote it down -- a note
// that follows a board there is that board's note. Where nobody did, the order is top to bottom down
// the canvas and a note belongs to the board it sits under.

export function documentOf(canvas, pageId, year) {
  const pages = pagesOf(canvas)
  const main = pages.filter((p) => !isRejected(p))
  const page = main.find((p) => p.id === pageId) || main[0] || pages[0]
  const folded = pages.filter((p) => isRejected(p) && siblingOf(p, canvas) === page)
  const decision = decisionOf(page, canvas, year)
  const parts = [{ page, rejected: false }, ...folded.map((p) => ({ page: p, rejected: true }))]
  const sections = parts.map(({ page: p, rejected }) => {
    const blocks = blocksOf(canvas, p).filter((b) => !(b.type === 'prose' && decision?.note != null && b.note.id === decision.note))
    for (const b of blocks) {
      if (b.type !== 'board') continue
      b.won = !rejected && decision?.board === b.board.file
      b.lost = rejected || lostTitle(b.board)
    }
    return { page: p, rejected, blocks }
  })
  return { page, pages: main, decision, sections }
}

function blocksOf(canvas, page) {
  const boards = (canvas.artboards || []).filter((b) => onPage(b, page, canvas))
  const notes = (canvas.annotations || []).filter((a) => onPage(a, page, canvas))
  const byFile = new Map(boards.map((b) => [b.file, b]))
  const byId = new Map(notes.map((a) => [a.id, a]))
  const blocks = []
  let last = null
  const used = new Set()
  if (canvas.reading?.length) {
    for (const k of canvas.reading) {
      if (byFile.has(k)) { last = { type: 'board', board: byFile.get(k), note: null }; blocks.push(last); used.add(k) }
      else if (byId.has(k)) {
        const a = byId.get(k); used.add(k)
        if (last && !last.note) last.note = a
        else { blocks.push({ type: 'prose', note: a }); last = null }
      }
    }
    // Anything on this page that the reading order left out still has to be somewhere.
    for (const b of boards) if (!used.has(b.file)) blocks.push({ type: 'board', board: b, note: null })
    for (const a of notes) if (!used.has(a.id)) blocks.push({ type: 'prose', note: a })
    return blocks
  }
  // No reading order: a note directly under a board is that board's; the rest are prose.
  const owner = new Map()
  for (const a of notes) {
    let best = null
    for (const b of boards) {
      const gap = a.y - (b.y + b.h)
      if (a.x >= b.x - 40 && a.x < b.x + b.w && gap >= -20 && gap < 600 && (!best || gap < best.gap)) best = { b, gap }
    }
    if (best && !owner.has(best.b.file)) owner.set(best.b.file, a)
  }
  const owned = new Set([...owner.values()])
  const items = [...boards.map((b) => ({ y: b.y, x: b.x, block: { type: 'board', board: b, note: owner.get(b.file) || null } })),
    ...notes.filter((a) => !owned.has(a)).map((a) => ({ y: a.y, x: a.x, block: { type: 'prose', note: a } }))]
  items.sort((p, q) => p.y - q.y || p.x - q.x)
  return items.map((i) => i.block)
}

// The board a canvas should open on: the one asked for, the one that won, or the one canvas.json's
// launch names. Null means fit everything, which is what a canvas with nothing decided still does.
export function launchBoard(canvas, pageId, year) {
  const pages = pagesOf(canvas)
  const page = pages.find((p) => p.id === pageId) || pages.find((p) => p.id === canvas.launch?.page) || pages[0]
  const d = isRejected(page) ? null : decisionOf(page, canvas, year)
  if (d?.board) return { page, file: d.board }
  const want = canvas.launch?.file
  if (want && (canvas.artboards || []).some((b) => b.file === want && onPage(b, page, canvas))) return { page, file: want }
  return { page, file: null }
}

// ---- the collections ---------------------------------------------------------------------------

const exists = async (p) => { try { await stat(p); return true } catch { return false } }

export async function collectionDirs(design) {
  const out = []
  if (await exists(path.join(design, 'canvas.json'))) out.push('')
  for (const e of await readdir(design, { withFileTypes: true })) {
    // A linked directory counts: the wall's boards are linked in from the hardware repository.
    if ((e.isDirectory() || e.isSymbolicLink()) && await exists(path.join(design, e.name, 'canvas.json'))) out.push(e.name)
  }
  return out
}

const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', mdash: '—', ndash: '–',
  hellip: '…', times: '×', middot: '·', rsquo: '’', lsquo: '‘', ldquo: '“', rdquo: '”' }
export const htmlText = (s) => s.replace(/<[^>]+>/g, '')
  .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(+d))
  .replace(/&([a-z]+);/gi, (m, n) => ENT[n.toLowerCase()] ?? m)
  .replace(/\s+/g, ' ').trim()

// When each collection last changed: when a board in it was last drawn. canvas.json is left out on
// purpose -- giving every collection an area touched all forty of them in one commit, and a note
// moved on a canvas is not new work. One git call for all of design/, kept for a minute; a directory
// git does not know -- linked in from another repository, or new and uncommitted -- uses its files.
const datesCache = new Map()
async function gitDates(design) {
  const hit = datesCache.get(design)
  if (hit && Date.now() - hit.at < 60_000) return hit.map
  const map = new Map()
  const out = await new Promise((res) => execFile('git', ['log', '--format=%x00%cs', '--name-only', '--', '.'],
    { cwd: design, maxBuffer: 64 << 20 }, (e, stdout) => res(e ? '' : stdout)))
  let date = null
  for (const line of out.split('\n')) {
    if (line.startsWith('\0')) { date = line.slice(1); continue }
    if (!line || !date || /(^|\/)canvas\.json$/.test(line)) continue
    const rel = line.replace(/^design\//, '')
    const dir = rel.includes('/') ? rel.split('/')[0] : ''
    if (!map.has(dir)) map.set(dir, date)
  }
  datesCache.set(design, { at: Date.now(), map })
  return map
}

async function touched(dir) {
  let newest = 0
  try {
    for (const e of await readdir(dir)) {
      if (!/\.dc\.html$/.test(e)) continue
      newest = Math.max(newest, (await stat(path.join(dir, e))).mtimeMs)
    }
  } catch { /* nothing to read is no date */ }
  return newest ? new Date(newest).toISOString().slice(0, 10) : null
}

// Everything the front page and search need about one collection.
export async function describe(design, dir, dates) {
  const base = path.join(design, dir)
  const canvas = JSON.parse(await readFile(path.join(base, 'canvas.json'), 'utf8'))
  let name = canvas.name || dir || 'design/'
  let blurb = canvas.about || ''
  if (await exists(path.join(base, 'index.html'))) {
    const html = await readFile(path.join(base, 'index.html'), 'utf8')
    const h1 = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)
    const p = html.match(/<\/h1>\s*<p[^>]*>([\s\S]*?)<\/p>/i)
    if (h1 && !canvas.name) name = htmlText(h1[1])
    if (p && !canvas.about) blurb = htmlText(p[1])
  }
  if (!blurb) {
    const first = (canvas.annotations || [])[0]
    if (first) { const { head, body } = splitNote(first.text); blurb = body[0] || head }
  }
  const linked = dir ? (await lstat(base)).isSymbolicLink() : false
  const areas = canvas.areas?.length ? canvas.areas : [linked ? 'Hardware' : 'Not sorted yet']
  const gitDate = !linked ? dates?.get(dir) : null
  const fileDate = gitDate ? null : await touched(base)
  const year = +(gitDate || fileDate || new Date().toISOString()).slice(0, 4)
  const pages = pagesOf(canvas).map((p) => ({ ...p, rejected: isRejected(p), decision: isRejected(p) ? null : decisionOf(p, canvas, year) }))
  const main = pages.filter((p) => !p.rejected)
  const decided = main.filter((p) => p.decision)
  const decidedOn = decided.map((p) => p.decision.on).filter(Boolean).sort().pop() || null
  const date = [gitDate, fileDate, decidedOn].filter(Boolean).sort().pop() || null
  const status = decided.length && decided.length === main.length ? 'chosen' : decided.length ? 'partly' : 'open'
  const chose = decided.length === 1 ? decided[0].decision.chose
    : decided.length > 1 ? `${decided.length} of ${main.length} questions` : null
  const hero = decided.find((p) => p.decision.board)?.decision.board || canvas.launch?.file || canvas.artboards?.[0]?.file
  const heroBoard = (canvas.artboards || []).find((b) => b.file === hero) || null
  return { dir, name, blurb, canvas, areas, linked, date, status, chose, guessed: decided.some((p) => p.decision.source === 'guessed'),
    pages, hero: heroBoard, boards: (canvas.artboards || []).length, notes: (canvas.annotations || []).length, year }
}

export async function allCollections(design) {
  const dates = await gitDates(design)
  const all = []
  for (const d of await collectionDirs(design)) {
    try { all.push(await describe(design, d, dates)) } catch (e) { console.warn(`design/${d}: ${e.message}`) }
  }
  return all.sort((a, b) => String(b.date).localeCompare(String(a.date)) || a.name.localeCompare(b.name))
}

// The front page's groups: an area per heading, newest area first, newest collection first inside it.
// A collection in two areas is under both.
export function byArea(collections) {
  const areas = new Map()
  for (const c of collections) for (const a of c.areas) {
    if (!areas.has(a)) areas.set(a, [])
    areas.get(a).push(c)
  }
  const last = ['Tools', 'Hardware', 'Not sorted yet']
  return [...areas.entries()].map(([area, list]) => ({ area, list, date: list[0]?.date || '' }))
    .sort((p, q) => last.indexOf(p.area) - last.indexOf(q.area) || String(q.date).localeCompare(String(p.date)))
}

// ---- search -------------------------------------------------------------------------------------
//
// One query over every collection's names, page names, board titles and note text. The whole phrase
// is looked for first; when nothing has it, every word has to be somewhere in the same place. Hits are
// grouped the way they are shown: a collection's page, with its decision beside it, the boards on it
// (every board on a page whose name matched, because that is the page you were looking for), and the
// notes, each with the sentence the words were in.

export function matcher(q) {
  const phrase = String(q || '').trim().toLowerCase().replace(/\s+/g, ' ')
  const words = phrase.split(' ').filter((w) => w.length > 1)
  return {
    phrase, words,
    test(s, loose) {
      const t = String(s || '').toLowerCase()
      return loose ? words.length > 0 && words.every((w) => t.includes(w)) : phrase.length > 1 && t.includes(phrase)
    },
    // Where to put the marks: [start, end) pairs into the original string.
    ranges(s, loose) {
      const t = String(s || '').toLowerCase(), out = []
      for (const w of loose ? words : [phrase]) {
        let i = 0
        while (w && (i = t.indexOf(w, i)) !== -1) { out.push([i, i + w.length]); i += w.length }
      }
      return out.sort((a, b) => a[0] - b[0])
    },
  }
}

export function excerpt(text, ranges, room = 90) {
  const flat = String(text).replace(/\s+/g, ' ')
  if (!ranges.length) return { text: flat.slice(0, room * 2), ranges: [] }
  const [s] = ranges[0]
  let a = Math.max(0, s - room), b = Math.min(flat.length, s + room * 1.4)
  if (a > 0) a = flat.indexOf(' ', a) + 1
  if (b < flat.length) b = flat.lastIndexOf(' ', b)
  return { text: (a > 0 ? '…' : '') + flat.slice(a, b) + (b < flat.length ? '…' : ''),
    ranges: ranges.filter(([x, y]) => x >= a && y <= b).map(([x, y]) => [x - a + (a > 0 ? 1 : 0), y - a + (a > 0 ? 1 : 0)]) }
}

export function search(collections, q) {
  const m = matcher(q)
  if (!m.phrase || m.phrase.length < 2) return { q: m.phrase, groups: [], counts: { boards: 0, notes: 0, pages: 0 } }
  const run = (loose) => {
    const groups = []
    for (const c of collections) {
      // The folder counts as a name: it is what a session in another checkout tells you to look for.
      const nameHit = m.test(c.name, loose) || m.test(c.dir.replace(/[-_]/g, ' '), loose) || m.test(c.dir, loose)
      for (const p of c.pages) {
        const pageHit = m.test(p.name, loose)
        const owner = p.rejected ? siblingOf(p, c.canvas) : p
        const decision = c.pages.find((x) => x.id === owner?.id)?.decision || null
        const boards = (c.canvas.artboards || []).filter((b) => onPage(b, p, c.canvas))
          .filter((b) => pageHit || m.test(b.title, loose) || m.test(b.file, loose))
          .map((b) => ({ file: b.file, title: b.title || b.file, w: b.w, h: b.h,
            won: !p.rejected && decision?.board === b.file, lost: p.rejected || lostTitle(b), ranges: m.ranges(b.title, loose) }))
        const notes = (c.canvas.annotations || []).filter((a) => onPage(a, p, c.canvas) && m.test(a.text, loose)).map((a) => {
          const { head, body } = splitNote(a.text)
          const h = sentenceCase(head)
          const rest = body.join(' ').replace(/\s+/g, ' ')
          const inHead = m.ranges(h, loose)
          return { id: a.id ?? null, head: h, headRanges: inHead, decision: DECIDED_HEAD.test(head),
            ...excerpt(rest || h, m.ranges(rest || h, loose)), rejected: p.rejected }
        })
        if (pageHit || boards.length || notes.length) {
          // A rejected page's hits sit with the page that beat it, after its own.
          const home = p.rejected && groups.find((g) => g.dir === c.dir && g.w === (c.w || null) && g.page.id === owner?.id)
          if (home) { home.boards.push(...boards); home.notes.push(...notes); continue }
          groups.push({ dir: c.dir, w: c.w || null, where: c.where || null, waiting: !!c.waiting, name: c.name, nameHit, docPage: owner?.id ?? null,
            page: { id: owner?.id ?? p.id, name: owner?.name ?? p.name, rejected: false, ranges: m.ranges(owner?.name ?? p.name, loose) },
            decision, date: c.date, boards, notes })
        } else if (nameHit && p === c.pages[0]) {
          groups.push({ dir: c.dir, w: c.w || null, where: c.where || null, waiting: !!c.waiting, name: c.name, nameHit, docPage: p.id ?? null, page: { id: p.id, name: p.name, rejected: false, ranges: [] },
            decision, date: c.date, boards: [], notes: [] })
        }
      }
    }
    return groups
  }
  let groups = run(false)
  const loose = !groups.length
  if (loose) groups = run(true)
  // A rejected page's hits sit with the page that beat it, and a decided page comes before an open one.
  // A collection whose name or folder is what was typed is what was looked for: it comes first, ahead
  // of any number of notes that only have the words.
  groups.sort((a, b) => (b.nameHit - a.nameHit) || (b.boards.length + b.notes.length) - (a.boards.length + a.notes.length)
    || String(b.date).localeCompare(String(a.date)))
  // The decision first among a page's notes, then the rest as the canvas has them; losers last.
  for (const g of groups) g.notes.sort((a, b) => (b.decision - a.decision) || (a.rejected - b.rejected))
  const counts = { boards: 0, notes: 0, pages: 0 }
  for (const g of groups) { counts.boards += g.boards.length; counts.notes += g.notes.length; if (g.page.ranges.length) counts.pages++ }
  return { q: m.phrase, loose, groups, counts }
}

// ---- other checkouts ------------------------------------------------------------------------------
//
// Several sessions work in this repository at once, each in its own worktree on its own branch, and a
// session draws its boards in its own one. Until that branch is merged, a collection drawn there does
// not exist to a viewer started here -- and it is not merged until somebody has picked, which is the
// thing the session is waiting for. So the viewer asks git, each time the page is drawn (a checkout
// changes branch within the hour), what every other checkout has in design/ that this one has not:
// committed on its branch since it left this one, or not committed yet. That is design/artboards/'s
// "From other checkouts", direction A, decided 5 October 2026.

const git = (cwd, args) => new Promise((res) => execFile('git', args, { cwd, maxBuffer: 16 << 20 },
  (e, out) => res(e ? null : String(out))))

// Every worktree of the repository design/ is in, but this one.
export async function worktrees(design) {
  const root = path.dirname(design)
  const out = await git(root, ['worktree', 'list', '--porcelain'])
  if (!out) return []
  const here = (await git(root, ['rev-parse', '--show-toplevel']))?.trim()
  const list = []
  for (const block of out.trim().split(/\n\n+/)) {
    const wt = block.match(/^worktree (.+)$/m)?.[1]
    if (!wt || path.resolve(wt) === path.resolve(here || root) || /^prunable/m.test(block)) continue
    const branch = block.match(/^branch refs\/heads\/(.+)$/m)?.[1] || null
    const head = block.match(/^HEAD (\w+)$/m)?.[1]
    list.push({ path: wt, name: path.basename(wt), branch, ref: branch || head })
  }
  return list
}

// Which collections a checkout has new or changed, from git: what its branch changed in design/ since
// it left this checkout's branch, and what is not committed there yet. A dir means design/<dir>/.
export async function changedIn(design, w) {
  const root = path.dirname(design)
  const dirs = new Map()
  const note = (file, how) => {
    const m = String(file).match(/^design\/([^/]+)\//)
    if (!m) return
    const d = dirs.get(m[1]) || { files: new Set(), uncommitted: false }
    d.files.add(file); if (how === 'dirty') d.uncommitted = true
    dirs.set(m[1], d)
  }
  const diff = await git(root, ['diff', '--name-only', '--no-renames', `HEAD...${w.ref}`, '--', 'design/'])
  for (const f of (diff || '').split('\n').filter(Boolean)) note(f, 'committed')
  const st = await git(w.path, ['status', '--porcelain', '--untracked-files=all', '--', 'design/'])
  for (const line of (st || '').split('\n').filter(Boolean)) note(line.slice(3).replace(/^.* -> /, ''), 'dirty')
  const ahead = +((await git(root, ['rev-list', '--count', `HEAD..${w.ref}`])) || 0)
  const subject = (await git(w.path, ['log', '-1', '--format=%s']))?.trim() || ''
  return { dirs, ahead, subject }
}

let elsewhereCache = { at: 0, design: null, list: null }
export async function elsewhere(design, here, { fresh = false } = {}) {
  if (!fresh && elsewhereCache.list && elsewhereCache.design === design && Date.now() - elsewhereCache.at < 60_000) return elsewhereCache.list
  const mine = new Map((here || []).map((c) => [c.dir, c]))
  const out = []
  for (const w of await worktrees(design)) {
    const { dirs, ahead, subject } = await changedIn(design, w)
    const theirs = path.join(w.path, 'design')
    const dates = await gitDates(theirs)
    for (const [dir, d] of dirs) {
      if (!await exists(path.join(theirs, dir, 'canvas.json'))) continue // removed there, or only its boards moved
      let c
      try { c = await describe(theirs, dir, dates) } catch { continue }
      const ours = mine.get(dir)
      const kind = ours ? 'changed' : 'new'
      // Waiting: a page of directions there, with nothing on it saying what won, that is not already
      // a page here -- a whole new collection, or a new question added to one.
      const ourPages = new Set((ours?.pages || []).map((p) => p.id))
      const waiting = c.pages.some((p) => !p.rejected && !p.decision && (kind === 'new' || !ourPages.has(p.id)))
      out.push({ ...c, w: w.name, where: { name: w.name, path: w.path, branch: w.branch, ahead, subject },
        kind, waiting, changedFiles: d.files.size, uncommitted: d.uncommitted })
    }
  }
  out.sort((a, b) => (b.waiting - a.waiting) || String(b.date).localeCompare(String(a.date)))
  elsewhereCache = { at: Date.now(), design, list: out }
  return out
}

// Where a collection's files are served from: its own folder here, or /w/<checkout>/ for one elsewhere.
export const filesOf = (c) => c.w ? `w/${c.w}${c.dir ? '/' + c.dir : ''}` : c.dir
