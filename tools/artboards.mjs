#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Every design artboard in a browser, laid out the way canvas.json says it is laid out.
//
//   tools/dev.sh design            the index of every collection, opened in a browser
//   node tools/artboards.mjs       the same thing without the wrapper
//   node tools/artboards.mjs --port 8410 --no-open
//
// The boards were drawn on a canvas -- canvas.json carries an x, a y and a width for every
// board AND for every annotation, which is the argument for the board sitting next to it. Open
// a .dc.html on its own and all of that is gone: you get one screen with no neighbours and no
// note saying why it is that way. Four directories grew a make-index.py to paste some of it
// back as a scrolling page; the other eight never did, and the four that did have to be re-run
// by hand or they drift from the canvas they were generated from.
//
// So: nothing is generated to disk here. The server reads canvas.json on every request and
// draws the canvas as a canvas -- pan, zoom, boards where the designer put them, notes beside
// them. Change canvas.json, reload the tab, and the two cannot disagree because there is only
// one of them. The stacked reading view is still here (press r) for the boards in an order;
// where a directory has a hand-written index.html, that prose is what the index card shows.
//
// No dependencies, and no build. Node's own http is all of it, which matters because looking at
// the screens is the one thing in this checkout that is supposed to need nothing installed.
import { createServer } from 'node:http'
import { readFile, readdir, stat } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DESIGN = path.join(HERE, '..', 'design')

const argv = process.argv.slice(2)
const arg = (name, fallback) => { const i = argv.indexOf(name); return i === -1 ? fallback : argv[i + 1] }
const PORT = Number(arg('--port', process.env.PORT || 8402))
const OPEN = !argv.includes('--no-open')

// ---- reading the canvases ----------------------------------------------------------------
// A collection is a directory holding a canvas.json. design/ itself is one of them; it is the
// panel's own boards and it is the reason `dir` can be the empty string throughout.

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

async function exists(p) { try { await stat(p); return true } catch { return false } }

async function collections() {
  const out = []
  if (await exists(path.join(DESIGN, 'canvas.json'))) out.push('')
  for (const e of await readdir(DESIGN, { withFileTypes: true })) {
    if (e.isDirectory() && await exists(path.join(DESIGN, e.name, 'canvas.json'))) out.push(e.name)
  }
  return out
}

// The display name and the sentence under it are never invented here. Where a directory has an
// index.html somebody wrote by hand, its h1 and first paragraph are the best description of the
// collection that exists, so they are what gets shown; everywhere else the directory name is the
// honest answer and the count of boards says the rest.
async function describe(dir) {
  const base = path.join(DESIGN, dir)
  const canvas = JSON.parse(await readFile(path.join(base, 'canvas.json'), 'utf8'))
  const written = await exists(path.join(base, 'index.html'))
  let name = dir || 'design/'
  let blurb = ''
  if (written) {
    const html = await readFile(path.join(base, 'index.html'), 'utf8')
    const h1 = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)
    const p = html.match(/<\/h1>\s*<p[^>]*>([\s\S]*?)<\/p>/i)
    const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', mdash: '\u2014',
                  ndash: '\u2013', hellip: '\u2026', times: '\u00d7', middot: '\u00b7', rsquo: '\u2019', lsquo: '\u2018' }
    const text = (s) => s.replace(/<[^>]+>/g, '')
      .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(+d))
      .replace(/&([a-z]+);/gi, (m, n) => ENT[n.toLowerCase()] ?? m)
      .replace(/\s+/g, ' ').trim()
    if (h1) name = text(h1[1])
    if (p) blurb = text(p[1])
  }
  return { dir, name, blurb, written, canvas }
}

const pagesOf = (c) => c.pages?.length ? c.pages : [{ id: null, name: null }]
const onPage = (item, page) => page == null || (item.page ?? null) === page || (item.page == null && page === firstPageId)
let firstPageId = null

// ---- the pages ------------------------------------------------------------------------------

const SHELL = `
  :root { color-scheme: dark; --bg:#08090c; --ink:#f1eee8; --dim:#b9b5ad; --faint:#7f7d77; --amber:#e9b872; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 "Instrument Sans", -apple-system, system-ui, sans-serif; }
  a { color: var(--amber); }
  .bar { position:fixed; inset:0 0 auto 0; height:52px; z-index:50; display:flex; align-items:center; gap:18px;
         padding:0 18px; background:rgba(8,9,12,.82); backdrop-filter:blur(18px) saturate(1.4);
         border-bottom:1px solid rgba(241,238,232,.09); }
  .bar .home { text-decoration:none; color:var(--faint); font-size:13px; letter-spacing:.06em; }
  .bar .home:hover { color:var(--ink); }
  .bar h1 { font-size:15px; font-weight:500; margin:0; letter-spacing:-.01em; }
  .bar .spacer { flex:1; }
  .bar button, .tab { background:transparent; border:1px solid rgba(241,238,232,.16); color:var(--dim);
         font:inherit; font-size:12.5px; padding:5px 11px; border-radius:7px; cursor:pointer; }
  .bar button:hover, .tab:hover { color:var(--ink); border-color:rgba(241,238,232,.36); }
  .tab.on { color:#08090c; background:var(--amber); border-color:var(--amber); }
  .tabs { display:flex; gap:6px; }
  .count { font-size:12.5px; color:var(--faint); font-variant-numeric:tabular-nums; }
`

function indexPage(items) {
  const card = (c) => {
    const boards = c.canvas.artboards || []
    const hero = boards[0]
    const q = c.dir ? `?d=${encodeURIComponent(c.dir)}` : ''
    const src = hero ? `/${c.dir ? c.dir + '/' : ''}${hero.file}` : ''
    // The hero is the real board in an iframe, not a screenshot -- a screenshot is one more
    // thing that goes stale, and these boards are cheap enough to draw at 1/6 size.
    return `<a class="card" href="/canvas${q}">
      <div class="shot" style="--w:${hero?.w || 1440}px; --h:${hero?.h || 900}px">
        ${hero ? `<iframe src="${esc(src)}" width="${hero.w}" height="${hero.h}" loading="lazy" scrolling="no" tabindex="-1"></iframe>` : ''}
      </div>
      <div class="meta">
        <h2>${esc(c.name)}</h2>
        <p class="n">${boards.length} board${boards.length === 1 ? '' : 's'} &middot; ${(c.canvas.annotations || []).length} note${(c.canvas.annotations || []).length === 1 ? '' : 's'}${c.canvas.pages?.length ? ` &middot; ${c.canvas.pages.length} pages` : ''}</p>
        ${c.blurb ? `<p class="blurb">${esc(c.blurb)}</p>` : ''}
      </div>
    </a>`
  }
  return `<!doctype html><meta charset="utf-8"><title>The artboards</title>
<style>${SHELL}
  header { padding:96px 40px 0; max-width:74ch; }
  header h1 { font-size:42px; font-weight:400; letter-spacing:-.03em; margin:0 0 14px; }
  header p { color:var(--dim); margin:0 0 6px; }
  header .keys { color:var(--faint); font-size:13.5px; }
  main { display:grid; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); gap:30px; padding:44px 40px 120px; }
  .card { text-decoration:none; color:inherit; display:block; }
  .shot { position:relative; overflow:hidden; border-radius:13px; aspect-ratio:16/10;
          background:#101218; border:1px solid rgba(241,238,232,.08);
          box-shadow:0 26px 60px -34px rgba(0,0,0,.95); }
  .shot iframe { position:absolute; top:0; left:50%; border:0; transform-origin:0 0; pointer-events:none;
                 width:var(--w); height:var(--h); }
  .card:hover .shot { border-color:rgba(233,184,114,.5); }
  .meta { padding:14px 2px 0; }
  .meta h2 { font-size:16px; font-weight:500; margin:0 0 5px; letter-spacing:-.01em; }
  .n { margin:0; font-size:12px; letter-spacing:.09em; text-transform:uppercase; color:var(--faint); }
  .blurb { margin:9px 0 0; color:var(--dim); font-size:13.5px; line-height:1.5;
           display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
</style>
<header>
  <h1>The artboards</h1>
  <p>Every collection in <code>design/</code>, drawn from its <code>canvas.json</code> as you reload —
     boards where they were placed, with the notes that argue them.</p>
  <p class="keys">Inside a canvas: drag to pan, &#8984;-scroll or pinch to zoom, <b>f</b> fit, <b>1</b> full size,
     <b>r</b> read it as a page, double-click a board to fill the screen with it.</p>
</header>
<main>${items.map(card).join('')}</main>
<script>
  // Each hero is a full 1440-wide board shrunk into its card; the scale has to be measured
  // because the grid column width is whatever the window gives it.
  const fit = () => document.querySelectorAll('.shot').forEach(s => {
    const f = s.querySelector('iframe'); if (!f) return
    // by width for a wall board, by height for a phone board -- whichever keeps all of it in
    const k = Math.min(s.clientWidth / f.width, s.clientHeight / f.height)
    f.style.transform = 'translateX(' + (-f.width * k / 2) + 'px) scale(' + k + ')'
  })
  addEventListener('resize', fit); fit()
</script>`
}

function canvasPage(c) {
  const pages = pagesOf(c.canvas)
  const q = c.dir ? `?d=${encodeURIComponent(c.dir)}` : ''
  return `<!doctype html><meta charset="utf-8"><title>${esc(c.name)} — canvas</title>
<style>${SHELL}
  body { overflow:hidden; height:100vh; }
  #view { position:fixed; inset:52px 0 0 0; overflow:hidden; cursor:grab;
          background:radial-gradient(1200px 700px at 50% -10%, #12141b, #08090c 70%); }
  #view.drag { cursor:grabbing; }
  #world { position:absolute; top:0; left:0; transform-origin:0 0; will-change:transform; }
  .board { position:absolute; }
  .board .frame { position:absolute; inset:0; border-radius:12px; overflow:hidden;
                  background:#0d0f14; border:1px solid rgba(241,238,232,.10);
                  box-shadow:0 40px 90px -40px rgba(0,0,0,.95); }
  .board iframe { border:0; display:block; width:100%; height:100%; }
  /* The shield is why a drag that starts on a board still pans the canvas: an iframe would eat
     the pointer otherwise. A board that actually runs gives its pointer back on a click. */
  .board .shield { position:absolute; inset:0; z-index:2; }
  .board.live .shield { pointer-events:none; }
  .board.live .frame { border-color:rgba(233,184,114,.75); box-shadow:0 0 0 1px rgba(233,184,114,.45), 0 40px 90px -40px rgba(0,0,0,.95); }
  .board .pending { position:absolute; inset:0; display:grid; place-items:center; color:var(--faint); font-size:13px; }
  /* Labels counter-scale, so the overview still reads as a set of named screens at 12%. */
  .label { position:absolute; bottom:100%; left:0; margin-bottom:9px; white-space:nowrap;
           transform-origin:0 100%; transform:scale(var(--inv,1));
           max-width:calc(var(--bw) * var(--k, 1) * 1px); overflow:hidden; text-overflow:ellipsis;
           font-size:12px; letter-spacing:.09em; text-transform:uppercase; color:var(--faint); }
  #world.tiny .label { display:none; }
  .board.live .label { color:var(--amber); }
  .label .runs { color:var(--amber); }
  .note { position:absolute; border-left:2px solid rgba(233,184,114,.4); padding:2px 0 2px 20px; }
  .note h3 { font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:var(--amber);
             margin:0 0 11px; font-weight:500; }
  .note p { margin:0 0 11px; color:var(--dim); }
  #help { position:fixed; right:18px; bottom:18px; z-index:60; max-width:330px; padding:16px 18px;
          background:rgba(13,15,20,.94); border:1px solid rgba(241,238,232,.14); border-radius:12px;
          font-size:13px; color:var(--dim); display:none; }
  #help.on { display:block; }
  #help b { color:var(--ink); font-weight:500; }
  #help div { margin:5px 0; }
</style>
<div class="bar">
  <a class="home" href="/">&#8592; all boards</a>
  <h1>${esc(c.name)}</h1>
  <div class="tabs">${pages.length > 1 ? pages.map((p, i) => `<button class="tab" data-page="${esc(p.id)}">${esc(p.name || 'page ' + (i + 1))}</button>`).join('') : ''}</div>
  <span class="spacer"></span>
  <span class="count" id="zoom"></span>
  <button id="bfit">fit</button>
  <button id="bone">100%</button>
  <button onclick="location='/read${q}'">read</button>
  <button id="bhelp">?</button>
</div>
<div id="view"><div id="world"></div></div>
<div id="help">
  <div><b>drag</b> pan &middot; <b>&#8984;-scroll / pinch</b> zoom &middot; <b>scroll</b> pan</div>
  <div><b>f</b> fit everything &middot; <b>1</b> full size &middot; <b>+ &minus;</b> zoom</div>
  <div><b>double-click</b> a board to fill the screen with it</div>
  <div><b>click</b> a board marked <span style="color:var(--amber)">runs</span> to use it &middot; <b>esc</b> hands it back</div>
  <div><b>[ ]</b> pages &middot; <b>r</b> read as a page &middot; <b>?</b> this</div>
</div>
<script>
const DATA = ${JSON.stringify({ dir: c.dir, canvas: c.canvas })}
const BASE = DATA.dir ? '/' + DATA.dir + '/' : '/'
const view = document.getElementById('view'), world = document.getElementById('world')
const pages = ${JSON.stringify(pages)}
let page = pages[0].id
const st = { k: 1, x: 0, y: 0 }

const items = []            // {el, x, y, w, h, board?}  everything that lives in world space

function build() {
  world.textContent = ''; items.length = 0
  for (const b of DATA.canvas.artboards || []) {
    if (pages.length > 1 && (b.page ?? pages[0].id) !== page) continue
    const el = document.createElement('div')
    el.className = 'board'
    el.style.cssText = \`left:\${b.x}px; top:\${b.y}px; width:\${b.w}px; height:\${b.h}px; --bw:\${b.w}\`
    el.innerHTML = \`<div class="label">\${esc(b.title || b.file)}\${b.is_interactive ? ' <span class="runs">&middot; runs</span>' : ''}</div>
      <div class="frame"><div class="pending">\${esc(b.file)}</div></div><div class="shield"></div>\`
    el.dataset.src = BASE + b.file
    el.dataset.live = b.is_interactive ? '1' : ''
    world.append(el); items.push({ el, x: b.x, y: b.y, w: b.w, h: b.h, board: b })
  }
  for (const a of DATA.canvas.annotations || []) {
    if (pages.length > 1 && (a.page ?? pages[0].id) !== page) continue
    const [head, ...rest] = String(a.text).split('\\n\\n')
    const el = document.createElement('div')
    el.className = 'note'
    el.style.cssText = \`left:\${a.x}px; top:\${a.y}px; width:\${a.w}px\`
    el.innerHTML = '<h3>' + esc(head) + '</h3>' + rest.map(p => '<p>' + esc(p) + '</p>').join('')
    world.append(el); items.push({ el, x: a.x, y: a.y, w: a.w, h: 0 })
  }
  // A note's height is whatever the text wrapped to, and only the browser knows it. It is read
  // back after layout so that fit() frames the notes and not just the boards.
  requestAnimationFrame(() => { for (const it of items) if (!it.board) it.h = it.el.offsetHeight })
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.page === page))
}

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])) }

function bounds() {
  if (!items.length) return { x: 0, y: 0, w: 1440, h: 900 }
  const x0 = Math.min(...items.map(i => i.x)), y0 = Math.min(...items.map(i => i.y))
  const x1 = Math.max(...items.map(i => i.x + i.w)), y1 = Math.max(...items.map(i => i.y + (i.h || 200)))
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

function apply() {
  world.style.transform = \`translate(\${st.x}px, \${st.y}px) scale(\${st.k})\`
  world.style.setProperty('--inv', 1 / st.k)
  world.style.setProperty('--k', st.k)
  world.classList.toggle('tiny', st.k * 1440 < 150)   // narrower than a few words: drop the names
  document.getElementById('zoom').textContent = Math.round(st.k * 100) + '%'
  cull()
}

// Eighteen boards is eighteen full pages of CSS and script, and most of them are off-screen most
// of the time. A frame is only created once it is nearly in view -- and then kept, because a
// board that rebuilds itself every time you pan past it restarts its animations.
function cull() {
  const m = 400
  for (const it of items) {
    if (!it.board || it.mounted) continue
    const sx = st.x + it.x * st.k, sy = st.y + it.y * st.k
    if (sx > innerWidth + m || sy > innerHeight + m || sx + it.w * st.k < -m || sy + it.h * st.k < -m) continue
    it.mounted = true
    const f = document.createElement('iframe')
    f.src = it.el.dataset.src; f.setAttribute('scrolling', 'no'); f.loading = 'eager'
    it.el.querySelector('.frame').replaceChildren(f)
  }
}

function frame(b, pad = 90) {
  const k = Math.min((innerWidth - pad * 2) / b.w, (innerHeight - 52 - pad * 2) / b.h)
  st.k = Math.min(k, 2)
  st.x = (innerWidth - b.w * st.k) / 2 - b.x * st.k
  st.y = (innerHeight - 52 - b.h * st.k) / 2 - b.y * st.k
  apply()
}
const fit = () => frame(bounds())

function zoomAt(cx, cy, nk) {
  nk = Math.max(0.03, Math.min(4, nk))
  st.x = cx - (cx - st.x) * (nk / st.k); st.y = cy - (cy - st.y) * (nk / st.k); st.k = nk; apply()
}

// ---- input ----
let drag = null
view.addEventListener('pointerdown', e => {
  if (e.target.closest('.board.live') && !e.target.classList.contains('shield')) return
  drag = { x: e.clientX, y: e.clientY, ox: st.x, oy: st.y, moved: 0, t: e.target }
  view.setPointerCapture(e.pointerId); view.classList.add('drag')
})
view.addEventListener('pointermove', e => {
  if (!drag) return
  drag.moved = Math.max(drag.moved, Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y))
  st.x = drag.ox + (e.clientX - drag.x); st.y = drag.oy + (e.clientY - drag.y); apply()
})
view.addEventListener('pointerup', e => {
  const d = drag; drag = null; view.classList.remove('drag')
  if (!d || d.moved > 4) return
  // A click that did not turn into a drag: hand the board its pointer back, if it runs.
  const board = d.t.closest('.board')
  if (board && board.dataset.live) board.classList.add('live')
})
view.addEventListener('dblclick', e => {
  const b = e.target.closest('.board'); if (!b) return
  const it = items.find(i => i.el === b); if (it) frame(it)
})
view.addEventListener('wheel', e => {
  e.preventDefault()
  if (e.ctrlKey || e.metaKey) zoomAt(e.clientX, e.clientY - 52, st.k * Math.exp(-e.deltaY / 220))
  else { st.x -= e.deltaX; st.y -= e.deltaY; apply() }
}, { passive: false })

addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey) return
  const c = innerWidth / 2, m = (innerHeight - 52) / 2
  if (e.key === 'f') fit()
  else if (e.key === '1') zoomAt(c, m, 1)
  else if (e.key === '+' || e.key === '=') zoomAt(c, m, st.k * 1.25)
  else if (e.key === '-') zoomAt(c, m, st.k / 1.25)
  else if (e.key === 'Escape') document.querySelectorAll('.board.live').forEach(b => b.classList.remove('live'))
  else if (e.key === 'r') location = '/read${q}'
  else if (e.key === '?') document.getElementById('help').classList.toggle('on')
  else if (e.key === '[' || e.key === ']') {
    const i = pages.findIndex(p => p.id === page)
    const n = pages[(i + (e.key === ']' ? 1 : pages.length - 1)) % pages.length]
    if (n && n.id !== page) { page = n.id; build(); requestAnimationFrame(fit) }
  }
})
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  page = t.dataset.page; build(); requestAnimationFrame(fit)
})
document.getElementById('bfit').onclick = fit
document.getElementById('bone').onclick = () => zoomAt(innerWidth / 2, (innerHeight - 52) / 2, 1)
document.getElementById('bhelp').onclick = () => document.getElementById('help').classList.toggle('on')
addEventListener('resize', cull)

// launch.file says which board this canvas is really about; open on it rather than on the
// whole sprawl, the way canvas.json asks.
build()
requestAnimationFrame(() => {
  const want = DATA.canvas.launch || {}
  const one = want.view === 'focused' && items.find(i => i.board && i.board.file === want.file)
  one ? frame(one) : fit()
})
</script>`
}

// The stacked view: the boards in an order, each with the note that argues it. `reading` in
// canvas.json is that order where somebody wrote one down -- it interleaves note ids and file
// names. Where nobody did, top-to-bottom down the canvas is the order the canvas implies.
function readPage(c) {
  const notes = Object.fromEntries((c.canvas.annotations || []).map(a => [a.id, a]))
  const boards = Object.fromEntries((c.canvas.artboards || []).map(b => [b.file, b]))
  let order = c.canvas.reading
  if (!order?.length) {
    order = [...(c.canvas.artboards || []).map(b => ({ k: b.file, y: b.y, x: b.x })),
             ...(c.canvas.annotations || []).map(a => ({ k: a.id, y: a.y, x: a.x }))]
      .sort((p, q) => p.y - q.y || p.x - q.x).map(i => i.k)
  }
  const base = c.dir ? '/' + c.dir + '/' : '/'
  const parts = order.map((k) => {
    if (notes[k]) {
      const [head, ...rest] = String(notes[k].text).split('\n\n')
      return `<section class="note"><h2>${esc(head)}</h2>${rest.map(p => `<p>${esc(p)}</p>`).join('')}</section>`
    }
    const b = boards[k]; if (!b) return ''
    return `<figure style="--w:${b.w}px; --h:${b.h}px">
      <iframe src="${esc(base + b.file)}" width="${b.w}" height="${b.h}" loading="lazy" scrolling="no"></iframe>
      <figcaption>${esc(b.title || b.file)} &middot; <a href="${esc(base + b.file)}" target="_blank">open on its own</a></figcaption></figure>`
  })
  const q = c.dir ? `?d=${encodeURIComponent(c.dir)}` : ''
  return `<!doctype html><meta charset="utf-8"><title>${esc(c.name)} — the boards</title>
<style>${SHELL}
  main { display:flex; flex-direction:column; align-items:center; gap:40px; padding:104px 20px 120px; }
  figure { margin:0; width:min(var(--w), 100%); }
  figure .hold { overflow:hidden; }
  iframe { border:0; display:block; border-radius:13px; transform-origin:0 0;
           box-shadow:0 30px 80px -30px rgba(0,0,0,.9); }
  figcaption { margin-top:13px; font-size:12.5px; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); }
  .note { width:min(880px, 100%); border-left:2px solid rgba(233,184,114,.4); padding:4px 0 4px 22px; }
  .note h2 { font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:var(--amber); margin:0 0 12px; font-weight:500; }
  .note p { margin:0 0 12px; color:var(--dim); }
</style>
<div class="bar">
  <a class="home" href="/">&#8592; all boards</a>
  <h1>${esc(c.name)}</h1>
  <span class="spacer"></span>
  <button onclick="location='/canvas${q}'">canvas</button>
</div>
<main>${parts.join('')}</main>
<script>
  // Each board keeps its drawn size and is scaled into the column, so a 390-wide phone board is
  // not stretched to 1440 and a 1612-wide one is not cut off.
  function fit() {
    for (const f of document.querySelectorAll('figure')) {
      const i = f.querySelector('iframe'), k = Math.min(1, f.clientWidth / i.width)
      i.style.transform = 'scale(' + k + ')'
      f.style.height = (i.height * k + 34) + 'px'; f.style.overflow = 'hidden'
    }
  }
  addEventListener('resize', fit); fit()
</script>`
}

// ---- the runtime the boards were drawn against ----------------------------------------------
// A .dc.html is not a plain page. Inside <x-dc> the markup carries {{ dotted.paths }} and
// onClick="{{handler}}", and the <script data-dc-script> at the bottom is a `class Component
// extends DCLogic` whose renderVals() returns the object those paths are read from. Without a
// DCLogic on the page the sixteen boards that define one draw their templates verbatim: the
// sky comes out as the literal text {{f.sky}} and Main, Tones, Devices and nightfall/Main --
// the boards you would actually want to look at -- are the broken ones.
//
// The runtime is not lost. design/home-hub-panel.html is the canvas published as a page, and
// the tool's own file export is in there: `supportJs`, `reactUmd` and `reactDomUmd`, three
// template literals holding exactly the support.js and the React it writes beside an exported
// board. So this does not vendor a runtime into the repo and does not reimplement one -- it
// reads the copy that is already committed, and serves the same three files concatenated,
// because the boards here were exported asking only for support.js and expect React to have
// been put in front of it.
let supportCache
async function supportJs() {
  if (supportCache !== undefined) return supportCache
  try {
    const src = await readFile(path.join(DESIGN, 'home-hub-panel.html'), 'utf8')
    const parts = ['reactUmd', 'reactDomUmd', 'supportJs'].map((k) => literal(src, k))
    supportCache = parts.every(Boolean) ? parts.join('\n;\n') : null
  } catch { supportCache = null }
  if (supportCache === null) console.warn('no dc-runtime in design/home-hub-panel.html — the 16 boards with logic will draw their templates raw')
  return supportCache
}

// Pull one `name:`...`` template literal out of the bundle and undo the escaping it was
// written with, so what comes back is the file the tool would have exported.
function literal(src, name) {
  const at = src.indexOf(name + ':`')
  if (at === -1) return null
  let i = at + name.length + 2, out = ''
  for (; i < src.length; i++) {
    const c = src[i]
    if (c === '`') return unescapeTemplate(out)
    out += c
    if (c === '\\') { out += src[++i] }
  }
  return null
}

const SIMPLE = { n: '\n', r: '\r', t: '\t', b: '\b', f: '\f', v: '\v', 0: '\0' }
function unescapeTemplate(s) {
  let out = ''
  for (let i = 0; i < s.length; i++) {
    if (s[i] !== '\\') { out += s[i]; continue }
    const c = s[++i]
    if (c === 'u' && s[i + 1] === '{') { const e = s.indexOf('}', i); out += String.fromCodePoint(parseInt(s.slice(i + 2, e), 16)); i = e }
    else if (c === 'u') { out += String.fromCharCode(parseInt(s.substr(i + 1, 4), 16)); i += 4 }
    else if (c === 'x') { out += String.fromCharCode(parseInt(s.substr(i + 1, 2), 16)); i += 2 }
    else if (c === '\n') { /* a line continuation is nothing */ }
    else out += SIMPLE[c] ?? c          // \` \$ \\ and anything else is the character itself
  }
  return out
}

// ---- serving ---------------------------------------------------------------------------------

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.mp4': 'video/mp4', '.webm': 'video/webm' }

const send = (res, code, type, body) =>
  res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' }).end(body)

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x')
  const dir = url.searchParams.get('d') || ''
  try {
    if (url.pathname === '/') {
      const items = []
      for (const d of await collections()) items.push(await describe(d))
      return send(res, 200, TYPES['.html'], indexPage(items))
    }
    if (url.pathname === '/canvas' || url.pathname === '/read') {
      if (dir.includes('..') || path.isAbsolute(dir)) return send(res, 400, 'text/plain', 'no')
      const c = await describe(dir)
      return send(res, 200, TYPES['.html'], url.pathname === '/canvas' ? canvasPage(c) : readPage(c))
    }
    // Ninety-two of the ninety-three boards open with <script src="./support.js">, and no such
    // file has ever been in this checkout -- see supportJs() for where it is found instead.
    if (url.pathname.endsWith('/support.js')) {
      const js = await supportJs()
      return send(res, js === null ? 404 : 200, TYPES['.js'], js ?? 'no dc-runtime found')
    }
    // Everything else is a file in design/, at the path it really has -- which is what keeps
    // the relative links inside the boards, and the hand-written index.html pages, working.
    const file = path.join(DESIGN, decodeURIComponent(url.pathname))
    if (!file.startsWith(DESIGN + path.sep)) return send(res, 403, 'text/plain', 'outside design/')
    const body = await readFile(file)
    return send(res, 200, TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', body)
  } catch (e) {
    return send(res, e.code === 'ENOENT' ? 404 : 500, 'text/plain', String(e.message))
  }
})

server.on('error', (e) => {
  if (e.code === 'EADDRINUSE') {
    console.error(`something already holds :${PORT} — tools/dev.sh design --port ${PORT + 1}`)
    process.exit(1)
  }
  throw e
})

server.listen(PORT, async () => {
  const at = `http://localhost:${PORT}/`
  const n = (await collections()).length
  console.log(`${n} collections of boards at ${at}   (ctrl-c to stop)`)
  if (OPEN) spawn(process.platform === 'darwin' ? 'open' : 'xdg-open', [at], { stdio: 'ignore' }).unref()
})
