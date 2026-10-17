// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The artboard viewer's pages, as design/artboards/ drew them and as the household of this repository
// chose on 5 October 2026: A's contents and A's document, with C's canvas behind the Canvas switch.
//
//   contents   every collection one line, newest first, grouped by the part of the house it is about;
//              the search field at the top narrows the same page in place
//   document   one page of a collection read in order: the decision first, then each board with the
//              note that argues it beside it, the directions that lost folded in at the end
//   canvas     the boards where they were drawn, opening on the one that won, its note in a drawer
//   beside     a board next to the panel it became, at the same size -- the comparison AGENTS.md
//              asks for when a screen is built
//
// The chrome has a light and a dark theme, and Auto follows the computer. The boards never change
// with it: a board is the spec and keeps the colors it was drawn in.
import { esc, sentenceCase, splitNote, shortTitle, noteHeadFor, filesOf, shortDate, documentOf, launchBoard, byArea, pagesOf, onPage, isRejected } from './lib.mjs'

// ---- the chrome both themes share ---------------------------------------------------------------

const TOKENS_DARK = `--bg:#0d0e11; --pane:#121317; --surface:#17191e; --raise:#20232a; --scrim:rgba(5,6,8,.72);
  --ink:#f1eee8; --ink-2:#b9b5ad; --ink-3:#8a877f; --line:rgba(241,238,232,.08); --line-2:rgba(241,238,232,.16);
  --accent-rgb:233,184,114; --accent:rgb(var(--accent-rgb)); --accent-text:#e9b872; --accent-ink:#2a1c07;
  --ok-rgb:116,198,157; --ok:rgb(var(--ok-rgb)); --hl:rgba(233,184,114,.3);
  --shadow:0 30px 70px -36px rgba(0,0,0,.95); --pop:0 40px 120px -20px rgba(0,0,0,.9); color-scheme:dark;`
const TOKENS_LIGHT = `--bg:#f6f4ef; --pane:#eeebe4; --surface:#ffffff; --raise:#e9e5dd; --scrim:rgba(40,34,24,.34);
  --ink:#1c1b18; --ink-2:#55524b; --ink-3:#7a766d; --line:rgba(28,27,24,.09); --line-2:rgba(28,27,24,.17);
  --accent-rgb:192,138,53; --accent:rgb(var(--accent-rgb)); --accent-text:#875811; --accent-ink:#fff;
  --ok-rgb:47,138,92; --ok:rgb(var(--ok-rgb)); --hl:rgba(233,184,114,.5);
  --shadow:0 22px 50px -28px rgba(60,45,20,.38); --pop:0 40px 100px -30px rgba(60,45,20,.45); color-scheme:light;`

const CHROME = `
  :root { ${TOKENS_DARK} }
  :root[data-theme="light"] { ${TOKENS_LIGHT} }
  @media (prefers-color-scheme: light) { :root[data-theme="auto"] { ${TOKENS_LIGHT} } }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--ink); }
  body { font: 14px/1.5 "Instrument Sans", -apple-system, "SF Pro Text", system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
  a { color: inherit; text-decoration: none; }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; }
  mark { background: var(--hl); color: inherit; border-radius: 3px; padding: 0 2px; }
  code { font: .9em ui-monospace, "SF Mono", Menlo, monospace; }
  svg.i { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: none; }
  .dim { color: var(--ink-3); }
  .cap { font-size: 11.5px; letter-spacing: .11em; text-transform: uppercase; color: var(--ink-3); font-weight: 500; }
  .kbd { font-size: 11.5px; color: var(--ink-3); border: 1px solid var(--line-2); border-radius: 5px; padding: 0 6px; line-height: 19px; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .mark { display: inline-flex; align-items: center; gap: 10px; font-weight: 500; font-size: 15px; white-space: nowrap; }
  .mark b { width: 22px; height: 22px; border-radius: 6px; background: var(--accent); display: block; position: relative; flex: none; }
  .mark b::after { content: ''; position: absolute; left: 6px; top: 6px; width: 10px; height: 10px; border-radius: 2px; background: var(--bg); opacity: .9; }
  .search { display: flex; align-items: center; gap: 10px; height: 38px; padding: 0 10px 0 13px; border-radius: 10px;
            background: var(--surface); border: 1px solid var(--line-2); color: var(--ink-3); min-width: 0; }
  .search input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font: inherit; font-size: 14.5px; color: var(--ink); }
  .search input::placeholder { color: var(--ink-3); }
  .search:focus-within { border-color: rgba(var(--accent-rgb),.6); box-shadow: 0 0 0 3px rgba(var(--accent-rgb),.14); }
  .search .clear { display: none; }
  .search.has .clear { display: flex; }
  .search.has .kbd { display: none; }
  .seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 9px; background: var(--raise); flex: none; }
  .seg > * { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 9px; border-radius: 7px; color: var(--ink-3); cursor: pointer; font-size: 13px; white-space: nowrap; }
  .seg > .on { background: var(--surface); color: var(--ink); box-shadow: 0 1px 2px rgba(0,0,0,.18); }
  .chip { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 8px; border-radius: 6px; font-size: 12px; font-weight: 500; white-space: nowrap; }
  .chip i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .chip.chosen { color: var(--ok); background: rgba(var(--ok-rgb),.13); }
  .chip.open { color: var(--accent-text); background: rgba(var(--accent-rgb),.13); }
  .chip.no { color: var(--ink-3); background: var(--raise); }
  .pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pills button { height: 30px; padding: 0 12px; border-radius: 999px; display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); border: 1px solid var(--line-2); }
  .pills button.on { background: var(--ink); color: var(--bg); border-color: transparent; }
  /* a real board, drawn small: the board's own file in a frame, scaled -- never a screenshot that can go stale */
  .th { position: relative; overflow: hidden; border-radius: 7px; background: var(--raise); border: 1px solid var(--line); flex: none; display: block; }
  .th iframe { position: absolute; left: 0; top: 0; border: 0; transform-origin: 0 0; pointer-events: none; }
  .th.won { border-color: rgba(var(--ok-rgb),.8); box-shadow: 0 0 0 2px rgba(var(--ok-rgb),.35); }
  .th.lost { opacity: .5; }
  .toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: var(--ink); color: var(--bg); padding: 8px 14px; border-radius: 8px; font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 100; }
  .toast.on { opacity: 1; }
`

// Set before the first paint, so a light page never flashes dark.
const THEME_HEAD = `<script>try{document.documentElement.dataset.theme=localStorage.getItem('artboards-theme')||'auto'}catch(e){document.documentElement.dataset.theme='auto'}</script>`

export const ICON = {
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  auto: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  right: '<path d="M9 6l6 6-6 6"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  canvas: '<rect x="3" y="3" width="18" height="18" rx="2"/><rect x="6" y="7" width="6" height="4" rx="1"/><rect x="13" y="13" width="5" height="4" rx="1"/>',
  page: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 7h3"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  compare: '<rect x="3" y="5" width="8" height="14" rx="1.5"/><rect x="13" y="5" width="8" height="14" rx="1.5"/>',
  open: '<path d="M14 4h6v6M20 4l-8 8M10 5H5v14h14v-5"/>',
}
export const icon = (name, size = 16) => `<svg class="i" width="${size}" height="${size}" viewBox="0 0 24 24">${ICON[name]}</svg>`

const THEME_SEG = `<span class="seg theme" role="group" aria-label="Theme">
  <button data-theme-set="auto" title="Follow the computer">${icon('auto', 15)}</button>
  <button data-theme-set="light" title="Light">${icon('sun', 15)}</button>
  <button data-theme-set="dark" title="Dark">${icon('moon', 15)}</button></span>`

const THEME_JS = `
  function paintTheme() {
    const t = document.documentElement.dataset.theme
    document.querySelectorAll('[data-theme-set]').forEach(b => b.classList.toggle('on', b.dataset.themeSet === t))
  }
  document.querySelectorAll('[data-theme-set]').forEach(b => b.onclick = () => {
    document.documentElement.dataset.theme = b.dataset.themeSet
    try { localStorage.setItem('artboards-theme', b.dataset.themeSet) } catch (e) {}
    paintTheme()
  })
  paintTheme()
  function toast(t) { let el = document.querySelector('.toast'); if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.append(el) }
    el.textContent = t; el.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove('on'), 1400) }
  function copyLink(url) { (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => toast('Link copied'), () => prompt('The link', url)) }
`

const page = (title, css, body) => `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>${THEME_HEAD}
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&display=swap">
<style>${CHROME}${css}</style></head><body>${body}</body></html>`

// ---- small pieces both the server and the pages' own scripts draw -----------------------------
// Written once and sent to the browser with toString(), so a search result and the contents page
// draw a board the same way.

export function thumb(dir, b, w, h, cls) {
  const k = Math.min(w / b.w, h / b.h)
  const left = (w - b.w * k) / 2, top = (h - b.h * k) / 2
  const src = '/' + (dir ? dir + '/' : '') + b.file
  return '<span class="th ' + (cls || '') + '" style="width:' + w + 'px;height:' + h + 'px">' +
    '<iframe src="' + src.replace(/"/g, '&quot;') + '" width="' + b.w + '" height="' + b.h + '" loading="lazy" scrolling="no" tabindex="-1" ' +
    'style="left:' + left.toFixed(1) + 'px;top:' + top.toFixed(1) + 'px;transform:scale(' + k.toFixed(4) + ')"></iframe></span>'
}

export function marked(text, ranges) {
  const e = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
  let out = '', at = 0
  for (const [a, b] of ranges || []) { if (a < at) continue; out += e(text.slice(at, a)) + '<mark>' + e(text.slice(a, b)) + '</mark>'; at = b }
  return out + e(String(text).slice(at))
}

const statusChip = (c) => c.status === 'chosen' ? '<span class="chip chosen">Chosen</span>'
  : c.status === 'partly' ? '<span class="chip open">Partly</span>' : '<span class="chip open">Open</span>'

const clip = (s, n = 44) => String(s).length > n ? String(s).slice(0, n - 1).trimEnd() + '\u2026' : String(s)
const decisionChip = (d, long) => !d ? '' : `<span class="chip chosen" title="${esc(d.chose || '')}"><i></i>${d.on ? 'Chosen ' + esc(shortDate(d.on)) : 'Chosen'}${long && d.chose ? ' &middot; ' + esc(clip(d.chose)) : ''}</span>`

const q = (o) => '?' + Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&')
const kindOf = (b) => b.w === 1440 && b.h === 900 ? 'Wall' : b.w === 390 && b.h === 844 ? 'Phone' : 'Board'

// A note as prose: its heading in sentence case, a lead-in typed in capitals ("THE TAP.") set bold,
// For and Against set apart, and a paragraph laid out with spaces kept as it was typed.
export function noteHtml(note, { head = true, title = null } = {}) {
  const { head: raw, body } = splitNote(note?.text)
  const h = head ? noteHeadFor(raw, title) : ''
  const para = (p) => {
    if (/\n\s{2,}\S/.test(p) || /^\s{2,}/.test(p)) return `<pre>${esc(p)}</pre>`
    const lead = p.match(/^((?:[A-Z0-9][A-Z0-9'’,/&-]*\s+){0,8}[A-Z0-9][A-Z0-9'’,/&-]*[.:])(\s|$)/)
    const box = /^(FOR|AGAINST|THE CASE FOR|THE CASE AGAINST)\b/i.test(p) ? (/^(AGAINST|THE CASE AGAINST)/i.test(p) ? 'against' : 'for') : ''
    const text = lead && lead[1].length > 2 && lead[1] === lead[1].toUpperCase()
      ? `<b>${esc(sentenceCase(lead[1]))}</b>${esc(p.slice(lead[1].length))}` : esc(p)
    return box ? `<p class="${box}">${text}</p>` : `<p>${text.replace(/\n/g, '<br>')}</p>`
  }
  return (h ? `<h3>${esc(h)}</h3>` : '') + body.map(para).join('')
}

const NOTE_CSS = `
  .prose h3 { margin: 0 0 10px; font-size: 15.5px; font-weight: 600; color: var(--ink); letter-spacing: -.005em; line-height: 1.35; }
  .prose p { margin: 0 0 12px; font-size: 14px; line-height: 1.65; color: var(--ink-2); }
  .prose p b { color: var(--ink); font-weight: 600; }
  .prose p.for, .prose p.against { padding: 10px 14px; border-radius: 10px; }
  .prose p.for { background: rgba(var(--ok-rgb),.09); }
  .prose p.for b { color: var(--ok); }
  .prose p.against { background: var(--raise); }
  .prose pre { margin: 0 0 12px; font: 12.5px/1.55 ui-monospace, "SF Mono", Menlo, monospace; color: var(--ink-2); white-space: pre-wrap; background: var(--raise); border-radius: 8px; padding: 10px 12px; overflow-x: auto; }
`

// ---- contents ---------------------------------------------------------------------------------

// A card for a collection in another checkout: its branch, where it is, and whether it waits on a pick.
function awayCard(c) {
  const d = c.pages.find((p) => p.decision)?.decision
  const chip = c.waiting ? '<span class="chip wait">Waiting for you</span>'
    : c.kind === 'new' && d ? decisionChip(d, true) : c.kind === 'new' ? statusChip(c) : '<span class="chip no">Changed</span>'
  const meta = c.kind === 'new'
    ? `New &middot; ${c.boards} board${c.boards === 1 ? '' : 's'} &middot; in ${esc(c.where.name)}${c.where.ahead ? `, ${c.where.ahead} commit${c.where.ahead === 1 ? '' : 's'} ahead` : ''}`
    : `${c.changedFiles} file${c.changedFiles === 1 ? '' : 's'} &middot; in ${esc(c.where.name)}${c.where.subject ? ` &middot; &ldquo;${esc(c.where.subject)}&rdquo;` : ''}`
  return `<a class="ac${c.waiting ? ' wait' : ''}" href="/read${q({ d: c.dir, w: c.w })}">${c.hero ? thumb(filesOf(c), c.hero, 160, 100) : '<span class="th" style="width:160px;height:100px"></span>'}
    <span class="body"><span class="t">${esc(c.name)}</span>
      <span class="c">${chip}<span class="br">${esc(c.where.branch || 'detached')}</span>${c.uncommitted ? '<span class="br">not committed</span>' : ''}</span>
      <span class="m">${meta}</span>${c.waiting ? `<span class="go">Pick one ${icon('right', 14)}</span>` : ''}</span></a>`
}

export function contentsPage(collections, query = '', away = []) {
  const boards = collections.reduce((n, c) => n + c.boards, 0), notes = collections.reduce((n, c) => n + c.notes, 0)
  const checkouts = new Set(away.map((c) => c.w)).size
  const open = collections.filter((c) => c.status !== 'chosen').length
  const lately = collections.slice(0, 3)
  const row = (c) => `<a class="row" data-status="${c.status === 'chosen' ? 'decided' : 'open'}" href="/read${q({ d: c.dir, w: c.w })}">
      <span class="n">${esc(c.name)}</span><span class="w">${esc(c.chose || '')}</span>${statusChip(c)}<span class="d">${esc(shortDate(c.date))}</span></a>`
  const area = ({ area, list }) => `<section class="area"><h2><b>${esc(area)}</b><span class="dim">${list.length}</span></h2>${list.map(row).join('')}</section>`
  const card = (c) => `<a class="card" href="/read${q({ d: c.dir, w: c.w })}">${c.hero ? thumb(filesOf(c), c.hero, 330, 200) : '<span class="th" style="width:330px;height:200px"></span>'}
      <span class="t">${esc(c.name)}</span>
      <span class="m">${statusChip(c)}<span>${esc([c.chose, shortDate(c.date)].filter(Boolean).join(' · '))}</span></span></a>`
  return page('The artboards', NOTE_CSS + `
  .top { position: sticky; top: 0; z-index: 10; height: 60px; display: grid; grid-template-columns: 1fr minmax(0, 560px) 1fr; align-items: center; gap: 16px; padding: 0 24px; border-bottom: 1px solid var(--line); background: var(--bg); }
  .top .right { justify-self: end; }
  main { max-width: 1072px; margin: 0 auto; padding: 0 16px 120px; }
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; flex-wrap: wrap; margin-top: 32px; }
  h1 { margin: 0; font-size: 40px; line-height: 1.1; font-weight: 400; letter-spacing: -.03em; }
  .lead { margin: 8px 0 0; color: var(--ink-2); font-size: 15px; }
  .lately { display: grid; grid-template-columns: repeat(3, 330px); gap: 25px; margin-top: 10px; }
  .card { display: grid; gap: 0; }
  .card .t { font-size: 15px; font-weight: 500; margin-top: 12px; }
  .card .m { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 13px; color: var(--ink-3); min-width: 0; }
  .card .m span:last-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .areas { columns: 2; column-gap: 40px; margin-top: 38px; }
  .area { break-inside: avoid; margin-bottom: 26px; }
  .area h2 { display: flex; align-items: baseline; gap: 10px; margin: 0; padding-bottom: 8px; border-bottom: 1px solid var(--line-2); font-size: 13px; font-weight: 400; }
  .area h2 b { font-weight: 600; }
  .row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, auto) auto 54px; align-items: center; gap: 12px; height: 35px; border-bottom: 1px solid var(--line); font-size: 14px; }
  .row:hover .n { color: var(--accent-text); }
  .row .n { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row .w { font-size: 12.5px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 170px; }
  .row .d { font-size: 12.5px; color: var(--ink-3); text-align: right; font-variant-numeric: tabular-nums; }
  .row.hide { display: none; }
  .away { margin-top: 26px; }
  .away .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 10px; }
  .ac { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 16px; padding: 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--line); }
  .ac:hover { border-color: var(--line-2); }
  .ac.wait { border-color: rgba(var(--accent-rgb),.55); box-shadow: 0 0 0 3px rgba(var(--accent-rgb),.10); }
  .ac .body { display: grid; align-content: start; min-width: 0; }
  .ac .t { font-size: 15px; font-weight: 500; }
  .ac .c { display: flex; gap: 6px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
  .ac .m { font-size: 12.5px; color: var(--ink-3); margin-top: 8px; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .ac .go { font-size: 13px; color: var(--accent-text); font-weight: 500; margin-top: 8px; display: inline-flex; gap: 4px; align-items: center; }
  .away .more { margin-top: 10px; font-size: 13px; color: var(--ink-3); }
  .br { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 6px; font: 12px ui-monospace, "SF Mono", Menlo, monospace; color: var(--ink-2); background: var(--raise); white-space: nowrap; }
  .chip.wait { color: var(--accent-ink); background: var(--accent); }
  .folded { display: none; }
  .showfold { color: var(--accent-text); font-weight: 500; }
  #results { display: none; padding-top: 28px; }
  body.searching #contents { display: none; }
  body.searching #results { display: block; }
  .rhead { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; color: var(--ink-2); font-size: 15px; }
  .rhead b { color: var(--ink); font-weight: 500; }
  .grp { margin-bottom: 26px; }
  .grp .gh { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; font-size: 13px; color: var(--ink-3); }
  .grp .gh b { color: var(--ink); font-weight: 500; font-size: 14px; }
  .strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; padding: 4px 0 14px; }
  .bt { display: grid; gap: 7px; font-size: 12.5px; color: var(--ink-2); border-radius: 9px; padding: 4px; margin: -4px; }
  .bt .th { width: 100% !important; }
  .bt b { font-weight: 500; color: var(--ink); }
  .hit { display: grid; grid-template-columns: 22px 1fr auto; gap: 12px; padding: 12px 14px; border-radius: 10px; }
  .hit .h { font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .hit .x { font-size: 13.5px; color: var(--ink-2); margin-top: 3px; line-height: 1.5; }
  .hit .go { opacity: 0; display: flex; gap: 6px; align-items: center; font-size: 12.5px; color: var(--ink-3); align-self: start; }
  .sel { background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-2); }
  .sel .go { opacity: 1; }
  .keys { position: fixed; left: 0; right: 0; bottom: 0; display: none; gap: 18px; justify-content: center; padding: 12px; font-size: 12.5px; color: var(--ink-3); background: linear-gradient(transparent, var(--bg) 40%); }
  body.searching .keys { display: flex; }
  .empty { color: var(--ink-3); padding: 40px 0; }
  @media (max-width: 1100px) { .lately { grid-template-columns: repeat(2, minmax(0, 1fr)); } .lately .card:nth-child(3) { display: none; } .lately .th { width: 100% !important; } .strip { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
  @media (max-width: 860px) { .away .cards { grid-template-columns: 1fr; } }
  @media (max-width: 760px) { .row .w { display: none; } .top { grid-template-columns: 1fr auto; } .top .mark { display: none; } .areas { columns: 1; } .lately { grid-template-columns: 1fr; } .lately .card:nth-child(2) { display: none; } h1 { font-size: 32px; } }
`, `
<div class="top">
  <a class="mark" href="/"><b></b>Artboards</a>
  <label class="search" id="sbox">${icon('search')}<input id="q" autocomplete="off" spellcheck="false" placeholder="Search ${boards} boards and ${notes} notes${checkouts ? `, here and in ${checkouts} other checkout${checkouts === 1 ? '' : 's'}` : ''}" value="${esc(query)}">
    <span class="kbd">&#8984;K</span><button class="clear" id="clear" title="Clear">${icon('x', 15)}</button></label>
  <span class="right">${THEME_SEG}</span>
</div>
<main>
  <div id="contents">
    <div class="head">
      <div><h1>The artboards</h1><p class="lead">Every screen drawn before it was built, with the case for each. Newest first.</p></div>
      <div class="pills" id="filter"><button class="on" data-f="all">All ${collections.length}</button><button data-f="open">Open ${open}</button><button data-f="decided">Decided ${collections.length - open}</button></div>
    </div>
    ${away.length ? `<section class="away"><p class="cap" style="margin: 0;">From other checkouts <span class="dim" style="text-transform: none; letter-spacing: 0; font-size: 13px; margin-left: 8px;">${checkouts} of the checkouts beside this one ${checkouts === 1 ? 'has' : 'have'} boards that are not here yet</span></p>
      <div class="cards">${away.slice(0, 4).map(awayCard).join('')}</div>${away.length > 4 ? `<p class="more">${away.length - 4} more &middot; search finds them all</p>` : ''}</section>` : ''}
    <p class="cap" style="margin: 30px 0 0;">${away.length ? 'Lately, here' : 'Lately'}</p>
    <div class="lately">${lately.map(card).join('')}</div>
    <div class="areas">${byArea(collections).map(area).join('')}</div>
  </div>
  <div id="results"></div>
</main>
<div class="keys"><span><span class="kbd">&uarr;</span> <span class="kbd">&darr;</span> move</span><span><span class="kbd">&#8629;</span> open it in place, on its page</span><span><span class="kbd">&#8984;&#8629;</span> on the canvas</span><span><span class="kbd">esc</span> back to contents</span></div>
<script>
${THEME_JS}
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
${thumb.toString()}
${marked.toString()}
const ICON = ${JSON.stringify({ check: icon('check'), page: icon('page') })}
const SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const shortDate = iso => iso ? (+iso.slice(8, 10)) + ' ' + SHORT[+iso.slice(5, 7) - 1] : ''
const qs = o => '?' + Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&')
const short = t => { t = String(t || '').replace(/\\s+--\\s+/g, ' \\u2014 '); const c = t.search(/[:,(]/); return (c > 0 ? t.slice(0, c) : t).trim() }

const input = document.getElementById('q'), box = document.getElementById('sbox'), out = document.getElementById('results')
document.getElementById('filter').onclick = e => {
  const f = e.target.closest('button')?.dataset.f; if (!f) return
  document.querySelectorAll('#filter button').forEach(b => b.classList.toggle('on', b.dataset.f === f))
  document.querySelectorAll('.row').forEach(r => r.classList.toggle('hide', f !== 'all' && r.dataset.status !== f))
}

let hits = [], at = 0, seq = 0
function render(r) {
  if (!r.groups.length) { out.innerHTML = '<p class="empty">Nothing mentions <b>' + esc(r.q) + '</b>.</p>'; hits = []; return }
  const n = r.counts.boards + r.counts.notes, cols = new Set(r.groups.map(g => g.dir)).size
  let h = '<div class="rhead"><span><b>' + n + ' place' + (n === 1 ? '' : 's') + '</b> mention' + (n === 1 ? 's' : '') + ' <b>' + esc(r.q) + '</b>' + (r.loose ? ', every word somewhere' : '') +
    ', in ' + cols + ' collection' + (cols === 1 ? '' : 's') + '</span>' +
    '<span class="pills" id="kind"><button class="on" data-k="all">All</button><button data-k="board">Boards ' + r.counts.boards + '</button><button data-k="note">Notes ' + r.counts.notes + '</button></span></div>'
  const named = r.groups.some(g => g.nameHit), fold = named && r.loose
  let folded = false
  for (const g of r.groups) {
    if (fold && !g.nameHit && !folded) {
      folded = true
      const rest = r.groups.filter(x => !x.nameHit), n = rest.reduce((k, x) => k + x.boards.length + x.notes.length, 0)
      h += '<div class="grp"><div class="gh"><b>Elsewhere in the words</b><span>' + n + ' place' + (n === 1 ? '' : 's') + ' in ' + new Set(rest.map(x => x.dir)).size + ' collections &middot; every word somewhere, not the phrase</span><button class="showfold" id="showfold">Show them</button></div></div><div class="folded" id="fold">'
    }
    const doc = qs({ d: g.dir, w: g.w, p: g.docPage })
    const d = g.decision
    h += '<div class="grp"><div class="gh"><b>' + esc(g.name) + '</b>' + (g.page.name ? '&rsaquo;<span>' + marked(g.page.name, g.page.ranges) + '</span>' : '') +
      (g.waiting ? '<span class="chip wait">Waiting for you</span>' : '') +
      (d ? '<span class="chip chosen"><i></i>' + (d.on ? 'Chosen ' + shortDate(d.on) : 'Chosen') + (d.chose ? ' &middot; ' + esc(d.chose.length > 44 ? d.chose.slice(0, 43).trimEnd() + '\u2026' : d.chose) : '') + '</span>' : '') +
      (g.where ? '<span class="br">' + esc(g.where.branch || 'detached') + '</span><span>in ' + esc(g.where.name) + ' &middot; not here yet</span>' : '') + '</div>'
    if (g.boards.length) {
      h += '<div class="strip">' + g.boards.slice(0, 12).map(b => '<a class="bt hitme" data-kind="board" href="/read' + qs({ d: g.dir, w: g.w, p: g.docPage, b: b.file }) + '" data-canvas="/canvas' + qs({ d: g.dir, w: g.w, p: g.page.id, b: b.file }) + '">' +
        thumb(g.w ? 'w/' + g.w + (g.dir ? '/' + g.dir : '') : g.dir, b, 162, 101, b.won ? 'won' : b.lost ? 'lost' : '') + '<span><b>' + marked(short(b.title), b.ranges.filter(([x, y]) => y <= short(b.title).length)) + '</b>' + (b.lost ? ' &middot; not chosen' : '') + '</span></a>').join('') + '</div>'
    }
    for (const n of g.notes) {
      h += '<a class="hit hitme" data-kind="note" href="/read' + doc + (n.id ? '#n-' + encodeURIComponent(n.id) : '') + '" data-canvas="/canvas' + qs({ d: g.dir, w: g.w, p: g.page.id }) + '">' +
        '<span class="dim" style="padding-top:2px;' + (n.decision ? 'color:var(--ok)' : '') + '">' + (n.decision ? ICON.check : ICON.page) + '</span><span><span class="h"><span>' + marked(n.head, n.headRanges) + '</span>' +
        (n.rejected ? '<span class="chip no">Not chosen</span>' : '<span class="dim" style="font-weight:400;font-size:13px">&middot; note</span>') + '</span>' +
        '<span class="x" style="display:block">' + marked(n.text, n.ranges) + '</span></span><span class="go"><span class="kbd">&#8629;</span>open here</span></a>'
    }
    h += '</div>'
  }
  if (folded) h += '</div>'
  out.innerHTML = h
  const sf = document.getElementById('showfold')
  if (sf) sf.onclick = () => { document.getElementById('fold').classList.remove('folded'); sf.parentElement.parentElement.remove(); hits = [...out.querySelectorAll('.hitme')] }
  hits = [...out.querySelectorAll('.hitme')].filter(x => !x.closest('.folded')); at = 0; select(0)
  document.getElementById('kind').onclick = e => {
    const k = e.target.closest('button')?.dataset.k; if (!k) return
    document.querySelectorAll('#kind button').forEach(b => b.classList.toggle('on', b.dataset.k === k))
    out.querySelectorAll('.hitme').forEach(x => x.style.display = k === 'all' || x.dataset.kind === k ? '' : 'none')
    out.querySelectorAll('.strip').forEach(s => s.style.display = k === 'note' ? 'none' : '')
    hits = [...out.querySelectorAll('.hitme')].filter(x => x.style.display !== 'none'); select(0)
  }
}
function select(i) {
  if (!hits.length) return
  at = (i + hits.length) % hits.length
  hits.forEach((h, j) => h.classList.toggle('sel', j === at))
  hits[at].scrollIntoView({ block: 'nearest' })
}
let timer
function run() {
  const v = input.value.trim()
  box.classList.toggle('has', !!input.value)
  history.replaceState(null, '', v ? '/' + qs({ q: v }) : '/')
  if (v.length < 2) { document.body.classList.remove('searching'); return }
  const mine = ++seq
  fetch('/search' + qs({ q: v })).then(r => r.json()).then(r => { if (mine !== seq) return; document.body.classList.add('searching'); render(r) })
}
input.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 120) }
document.getElementById('clear').onclick = e => { e.preventDefault(); input.value = ''; run(); input.focus() }
addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); input.focus(); input.select(); return }
  if (e.key === '/' && document.activeElement !== input) { e.preventDefault(); input.focus(); return }
  if (!document.body.classList.contains('searching')) return
  if (e.key === 'ArrowDown') { e.preventDefault(); select(at + 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); select(at - 1) }
  else if (e.key === 'Enter' && hits[at]) { e.preventDefault(); location = (e.metaKey || e.ctrlKey) ? hits[at].dataset.canvas : hits[at].href }
  else if (e.key === 'Escape') { input.value = ''; run() }
})
if (input.value) run()
if (new URLSearchParams(location.search).has('find')) input.focus()
</script>`)
}

// ---- document -----------------------------------------------------------------------------------

export function documentPage(c, pageId, boardFile, year) {
  const doc = documentOf(c.canvas, pageId, year)
  const { page: pg, pages, decision } = doc
  const n = pages.length, i = pages.indexOf(pg)
  const area = c.areas[0]
  const boards = doc.sections.flatMap((s) => s.blocks.filter((b) => b.type === 'board'))
  const decisionNote = decision?.note != null ? (c.canvas.annotations || []).find((a) => a.id === decision.note) : null
  const banner = !decision ? '' : `<div class="decided">${icon('check', 20)}<span><b>Decided${decision.on ? ' ' + esc(shortDate(decision.on)) : ''}${decision.chose ? ' &mdash; ' + esc(decision.chose) + '.' : '.'}</b>
      ${decisionNote ? esc((decision.said || '').split(/(?<=\.)\s/).slice(0, 2).join(' ')) : decision.source === 'guessed' ? 'The directions that lost are kept at the end of this page, and nothing here says which one won: a <code>decided</code> on this page in canvas.json would.' : ''}</span>
      ${decision.board ? `<a class="jump" href="#b-${esc(decision.board)}">Go to ${esc(shortTitle((c.canvas.artboards || []).find((b) => b.file === decision.board)?.title || 'it').split(/\s+—\s+/)[0])} &darr;</a>` : ''}</div>`
  const outlineItem = (blk) => blk.type === 'board'
    ? `<a class="it${blk.lost ? ' lost' : ''}" href="#b-${esc(blk.board.file)}" data-to="b-${esc(blk.board.file)}"><span class="lbl">${esc(shortTitle(blk.board.title || blk.board.file))}</span>${blk.won ? `<span class="ok">${icon('check', 15)}</span>` : blk.lost ? '<span class="tag">not chosen</span>' : ''}</a>`
    : `<a class="it" href="#n-${esc(blk.note.id)}" data-to="n-${esc(blk.note.id)}"><span class="lbl">${esc(sentenceCase(splitNote(blk.note.text).head).slice(0, 60))}</span></a>`
  const rail = pages.map((p) => {
    const d = c.pages.find((x) => x.id === p.id)?.decision
    const here = p === pg
    return `<a class="pg${here ? ' here' : ''}" href="/read${q({ d: c.dir, w: c.w, p: p.id })}">${icon(here ? 'down' : 'right', 14)}<span class="lbl">${esc(p.name || c.name)}</span>${d ? '<span class="chip chosen">Chosen</span>' : pagesOf(c.canvas).length > 1 ? '<span class="chip open">Open</span>' : ''}</a>` +
      (here ? doc.sections.flatMap((s) => s.blocks).map(outlineItem).join('') : '')
  }).join('')
  const figure = (b, cls) => {
    const k = Math.min(620 / b.w, 560 / b.h, 1)
    return `<div class="fig">${thumb(filesOf(c), b, Math.round(b.w * k), Math.round(b.h * k), cls)}
      <div class="cap2"><span>${kindOf(b)} &middot; ${b.w} &times; ${b.h}</span><span class="acts">
        <a href="/${esc((filesOf(c) ? filesOf(c) + '/' : '') + b.file)}" target="_blank">${icon('open', 14)}Open alone</a>
        <button data-copy="/read${esc(q({ d: c.dir, w: c.w, p: pg.id, b: b.file }))}">${icon('link', 14)}Copy link</button>
        <a href="/beside${esc(q({ d: c.dir, w: c.w, b: b.file }))}">${icon('compare', 14)}Beside the panel</a>
        <a href="/canvas${esc(q({ d: c.dir, w: c.w, p: (b.page ?? pg.id), b: b.file }))}">${icon('canvas', 14)}On the canvas</a></span></div></div>`
  }
  const block = (blk) => {
    if (blk.type === 'prose') return `<section class="prose wide" id="n-${esc(blk.note.id)}">${noteHtml(blk.note)}</section>`
    const t = String(blk.board.title || blk.board.file).replace(/\s+--\s+/g, ' — ')
    const m = t.match(/^(.{1,40}?)\s+—\s+(.*)$/)
    const up = (x) => x[0].toUpperCase() + x.slice(1)
    return `<section class="bd" id="b-${esc(blk.board.file)}" data-board="${esc(blk.board.file)}">
      <div class="sec">${m ? `<span class="letter">${esc(m[1])}</span><h2>${esc(up(m[2]))}</h2>` : `<h2>${esc(t)}</h2>`}
        ${blk.won ? '<span class="chip chosen"><i></i>Chosen</span>' : blk.lost ? '<span class="chip no">Not chosen</span>' : ''}</div>
      <div class="pair">${figure(blk.board, blk.won ? 'won' : blk.lost ? 'lost' : '')}
        <div class="prose note">${blk.note ? `<div id="n-${esc(blk.note.id)}">${noteHtml(blk.note, { title: blk.board.title })}</div>` : '<p class="dim">No note sits beside this board.</p>'}</div></div></section>`
  }
  // From another checkout: where it lives and where a pick goes, then -- while nothing on this page is
  // decided -- the pick itself, the page's boards side by side, ahead of everything else.
  const where = !c.where ? '' : `<div class="where">${icon('canvas', 18)}<span><b>Not in this checkout yet.</b> Drawn in <b>${esc(c.where.name)}</b> on <b>${esc(c.where.branch || 'a detached commit')}</b>${c.where.ahead ? `, ${c.where.ahead} commit${c.where.ahead === 1 ? '' : 's'} ahead of this one` : ''}${c.uncommitted ? ', some of it not committed yet' : ''}. A pick made here goes back to the session working in ${esc(c.where.name)}; the boards arrive in this checkout when that branch is merged.</span></div>`
  const toPick = (c.where && !decision && !isRejected(pg)) ? (() => {
    const note = (c.canvas.annotations || []).find((a) => onPage(a, pg, c.canvas) && /^\s*to pick\b/i.test(splitNote(a.text).head))
    const said = note ? splitNote(note.text).body[0] : 'Nothing on this page says what was picked yet.'
    const bs = doc.sections[0].blocks.filter((b) => b.type === 'board').slice(0, 4)
    return `<div class="topick"><p><span class="cap">To pick</span><span>${esc(said)}</span></p><div class="pick">${bs.map((b) =>
      `<a href="#b-${esc(b.board.file)}">${thumb(filesOf(c), b.board, 252, 157)}<span><b>${esc(shortTitle(b.board.title || b.board.file).split(/\s+\u2014\s+/)[0])}</b>${esc((String(b.board.title || '').replace(/\s+--\s+/g, ' \u2014 ').match(/\s\u2014\s(.*)$/) || [, ''])[1] ? ' \u2014 ' + String(b.board.title).replace(/\s+--\s+/g, ' \u2014 ').split(' \u2014 ').slice(1).join(' \u2014 ') : '')}</span></a>`).join('')}</div></div>`
  })() : ''
  const sections = doc.sections.map((s) => (s.rejected ? `<div class="fold"><span class="cap">Not chosen</span><span class="dim">${esc(s.page.name || '')} &middot; kept with their cases, as the record of why the other one won</span></div>` : '') + s.blocks.map(block).join('')).join('')
  const sel = boardFile || ''
  return page(`${pg.name || c.name} — ${c.name}`, NOTE_CSS + `
  .top { position: fixed; left: 0; right: 0; top: 0; z-index: 10; height: 60px; display: flex; align-items: center; gap: 14px; padding: 0 24px; border-bottom: 1px solid var(--line); background: var(--bg); }
  .crumb { color: var(--ink-3); font-size: 14px; display: flex; align-items: center; gap: 8px; min-width: 0; white-space: nowrap; overflow: hidden; }
  .crumb b { color: var(--ink); font-weight: 400; overflow: hidden; text-overflow: ellipsis; }
  .top .search { width: 300px; height: 34px; margin-left: auto; }
  .rail { position: fixed; left: 0; top: 60px; bottom: 0; width: 272px; background: var(--pane); border-right: 1px solid var(--line); padding: 22px 16px 90px; overflow-y: auto; }
  .rail .ttl { padding: 0 8px 18px; }
  .rail .ttl b { font-size: 16px; font-weight: 500; line-height: 1.3; display: block; }
  .rail .pg { display: flex; align-items: center; gap: 8px; min-height: 32px; padding: 0 8px; font-size: 13.5px; font-weight: 500; margin-top: 4px; }
  .rail .pg .chip { margin-left: auto; height: 20px; font-size: 11.5px; }
  .rail .lbl { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .rail .it { display: flex; align-items: center; gap: 8px; height: 30px; padding: 0 8px 0 30px; font-size: 13.5px; color: var(--ink-2); border-radius: 7px; position: relative; }
  .rail .it:hover { color: var(--ink); }
  .rail .it.on { background: var(--surface); color: var(--ink); box-shadow: inset 0 0 0 1px var(--line); }
  .rail .it.on::before { content: ''; position: absolute; left: 14px; top: 9px; bottom: 9px; width: 2px; border-radius: 2px; background: var(--accent); }
  .rail .it.lost { color: var(--ink-3); }
  .rail .it .ok { color: var(--ok); margin-left: auto; display: flex; }
  .rail .it .tag { margin-left: auto; font-size: 12px; white-space: nowrap; }
  .rail .keys { position: fixed; left: 0; width: 272px; bottom: 0; padding: 14px 24px 18px; font-size: 12px; line-height: 2; color: var(--ink-3); background: linear-gradient(transparent, var(--pane) 30%); }
  main { margin-left: 272px; padding: 90px 56px 50vh; max-width: 1240px; }
  .eyebrow { font-size: 13px; color: var(--ink-3); }
  h1 { margin: 6px 0 0; font-size: 36px; line-height: 1.1; font-weight: 400; letter-spacing: -.03em; }
  .decided { display: grid; grid-template-columns: 22px 1fr auto; gap: 14px; align-items: start; margin-top: 22px; padding: 16px 20px; border-radius: 12px;
             background: rgba(var(--ok-rgb),.08); border: 1px solid rgba(var(--ok-rgb),.32); font-size: 14.5px; color: var(--ink-2); line-height: 1.55; }
  .decided > svg { color: var(--ok); margin-top: 1px; }
  .decided b { color: var(--ink); font-weight: 600; }
  .decided .jump { color: var(--accent-text); font-weight: 500; white-space: nowrap; }
  .where { display: grid; grid-template-columns: 22px 1fr; gap: 14px; margin-top: 22px; padding: 14px 18px; border-radius: 12px; background: rgba(var(--accent-rgb),.09); border: 1px solid rgba(var(--accent-rgb),.35); font-size: 14px; color: var(--ink-2); line-height: 1.55; }
  .where > svg { color: var(--accent-text); margin-top: 1px; }
  .where b { color: var(--ink); font-weight: 600; }
  .br { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 6px; font: 12px ui-monospace, "SF Mono", Menlo, monospace; color: var(--ink-2); background: var(--raise); white-space: nowrap; }
  .topick { margin-top: 30px; }
  .topick > p { display: flex; gap: 12px; align-items: baseline; margin: 0 0 14px; font-size: 15px; color: var(--ink-2); }
  .pick { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
  .pick a { display: grid; gap: 8px; font-size: 13px; color: var(--ink-2); }
  .pick a b { color: var(--ink); font-weight: 500; }
  .wide { max-width: 760px; margin-top: 40px; scroll-margin-top: 90px; }
  .bd { margin-top: 46px; scroll-margin-top: 84px; }
  .sec { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .sec .letter { font-size: 13px; letter-spacing: .1em; text-transform: uppercase; color: var(--ink-3); font-weight: 500; }
  .sec h2 { margin: 0; font-size: 21px; font-weight: 500; letter-spacing: -.015em; line-height: 1.3; }
  .pair { display: grid; grid-template-columns: 620px minmax(0, 400px); gap: 36px; margin-top: 16px; align-items: start; }
  .fig .cap2 { display: flex; align-items: center; gap: 16px; margin-top: 12px; font-size: 12.5px; color: var(--ink-3); flex-wrap: wrap; }
  .fig .acts { display: flex; gap: 14px; margin-left: auto; flex-wrap: wrap; }
  .fig .acts > * { display: inline-flex; align-items: center; gap: 6px; color: var(--ink-3); font-size: 12.5px; }
  .fig .acts > *:hover { color: var(--ink); }
  .note p:first-child { margin-top: 0; }
  .bd.on .th { box-shadow: 0 0 0 2px var(--accent); border-color: transparent; }
  .bd.on .th.won { box-shadow: 0 0 0 2px var(--accent), 0 0 0 5px rgba(var(--ok-rgb),.35); }
  .fold { margin-top: 70px; padding-top: 18px; border-top: 1px solid var(--line-2); display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; }
  @media (max-width: 1240px) { .pair { grid-template-columns: minmax(0, 620px); } .fig .th { max-width: 100%; } }
  @media (max-width: 860px) { .rail { display: none; } main { margin-left: 0; padding: 84px 16px 50vh; } .top .search, .crumb { display: none; } .fig .th { width: 100% !important; aspect-ratio: auto; } }
`, `
<div class="top">
  <a class="mark" href="/"><b></b>Artboards</a>
  <span class="crumb">/ ${esc(area)} / <b>${esc(c.name)}</b>${c.where ? `<span class="br">${esc(c.where.branch || 'detached')}</span>` : ''}</span>
  <label class="search">${icon('search')}<input id="q" autocomplete="off" placeholder="Search"><span class="kbd">&#8984;K</span></label>
  <span class="seg"><a class="on" href="/read${esc(q({ d: c.dir, w: c.w, p: pg.id }))}">${icon('page', 15)}Page</a><a id="tocanvas" href="/canvas${esc(q({ d: c.dir, w: c.w, p: pg.id }))}">${icon('canvas', 15)}Canvas</a></span>
  ${THEME_SEG}
</div>
<nav class="rail">
  <div class="ttl"><b>${esc(c.name)}</b><span class="dim" style="font-size:12.5px">${c.boards} boards &middot; ${c.notes} notes${n > 1 ? ' &middot; ' + n + ' pages' : ''}${c.date ? ' &middot; ' + esc(shortDate(c.date)) : ''}</span></div>
  ${rail}
  <div class="keys"><span class="kbd">j</span> <span class="kbd">k</span> next and last board<br><span class="kbd">c</span> this board on the canvas<br><span class="kbd">l</span> copy a link to this board</div>
</nav>
<main>
  <div class="eyebrow">${esc(area)} &middot; ${esc(c.name)}${n > 1 ? ` &middot; page ${i + 1} of ${n}` : ''}</div>
  <h1>${esc(pg.name || c.name)}</h1>
  ${where}
  ${banner}
  ${toPick}
  ${sections}
</main>
<script>
${THEME_JS}
const D = ${JSON.stringify({ dir: c.dir, w: c.w || null, page: pg.id, pages: pagesOf(c.canvas).map((p) => p.id) })}
const boards = [...document.querySelectorAll('section.bd')], items = [...document.querySelectorAll('.rail .it')]
const qs = o => '?' + Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&')
let cur = null
function mark(id, scroll) {
  const el = document.getElementById(id); if (!el) return
  items.forEach(it => it.classList.toggle('on', it.dataset.to === id))
  const b = el.closest('section.bd')
  boards.forEach(x => x.classList.toggle('on', x === b))
  if (b) { cur = b.dataset.board; history.replaceState(null, '', '/read' + qs({ d: D.dir, w: D.w, p: D.page, b: cur })) }
  document.getElementById('tocanvas').href = '/canvas' + qs({ d: D.dir, w: D.w, p: D.page, b: cur })
  const on = items.find(it => it.dataset.to === id); if (on) on.scrollIntoView({ block: 'nearest' })
  if (scroll) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
// The outline follows whatever is at the top third of the window.
const watch = new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) mark(e.target.id) }, { rootMargin: '-20% 0px -70% 0px' })
document.querySelectorAll('section.bd, section.prose').forEach(s => watch.observe(s))
document.querySelectorAll('[data-copy]').forEach(b => b.onclick = () => copyLink(location.origin + b.dataset.copy))
const step = d => { const i = boards.findIndex(b => b.dataset.board === cur); const n = boards[Math.max(0, Math.min(boards.length - 1, i + d))]; if (n) mark(n.id, true) }
const input = document.getElementById('q')
input.onkeydown = e => { if (e.key === 'Enter' && input.value.trim()) location = '/' + qs({ q: input.value.trim() }); if (e.key === 'Escape') input.blur() }
addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); input.focus(); return }
  if (e.metaKey || e.ctrlKey || e.altKey || document.activeElement === input) return
  if (e.key === 'j') step(1)
  else if (e.key === 'k') step(-1)
  else if (e.key === 'c') location = document.getElementById('tocanvas').href
  else if (e.key === 'l' && cur) copyLink(location.origin + '/read' + qs({ d: D.dir, w: D.w, p: D.page, b: cur }))
  else if (e.key === '/') { e.preventDefault(); input.focus() }
})
const want = ${JSON.stringify(sel)}
if (want && document.getElementById('b-' + want)) requestAnimationFrame(() => mark('b-' + want, false) || document.getElementById('b-' + want).scrollIntoView({ block: 'start' }))
else if (location.hash) requestAnimationFrame(() => { const el = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (el) el.scrollIntoView({ block: 'start' }) })
</script>`)
}

// ---- canvas -------------------------------------------------------------------------------------
// The boards where they were drawn, with C's three fixes: it opens on the board that won, at a zoom
// where that board and its neighbor can be seen; the pages are one menu; and a click on a board
// opens its note in a drawer at a size you can read.

export function canvasPage(c, pageId, boardFile, year) {
  const pages = pagesOf(c.canvas)
  const launch = launchBoard(c.canvas, pageId, year)
  const pg = launch.page
  const start = boardFile && (c.canvas.artboards || []).some((b) => b.file === boardFile && onPage(b, pg, c.canvas)) ? boardFile : launch.file
  // Each board's note, already set as prose, keyed by file -- the same pairing the document uses.
  const notes = {}, won = {}
  for (const p of pages.filter((x) => !isRejected(x))) {
    for (const s of documentOf(c.canvas, p.id, year).sections) for (const blk of s.blocks) {
      if (blk.type !== 'board') continue
      notes[blk.board.file] = blk.note ? noteHtml(blk.note, { title: blk.board.title }) : ''
      if (blk.won) won[blk.board.file] = true
    }
  }
  const pageMenu = pages.map((p, i) => {
    const d = isRejected(p) ? null : c.pages.find((x) => x.id === p.id)?.decision
    return `<button class="pm${p === pg ? ' on' : ''}${isRejected(p) ? ' sub' : ''}" data-page="${esc(p.id ?? '')}"><span>${esc(p.name || 'Page ' + (i + 1))}</span>${d ? '<span class="chip chosen">Chosen</span>' : isRejected(p) ? '<span class="chip no">Not chosen</span>' : ''}</button>`
  }).join('')
  const d = isRejected(pg) ? null : c.pages.find((x) => x.id === pg.id)?.decision
  return page(`${c.name} — canvas`, NOTE_CSS + `
  body { overflow: hidden; height: 100vh; }
  .bar { position: fixed; inset: 0 0 auto 0; height: 52px; z-index: 50; display: flex; align-items: center; gap: 12px; padding: 0 18px; background: var(--bg); border-bottom: 1px solid var(--line); }
  .bar .home { font-size: 13px; color: var(--ink-3); display: inline-flex; align-items: center; gap: 4px; }
  .bar .name { font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .btn { height: 32px; padding: 0 11px; border-radius: 8px; border: 1px solid var(--line-2); display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--ink-2); white-space: nowrap; }
  .btn:hover { color: var(--ink); }
  .btn.on { color: var(--ink); background: var(--surface); }
  .spacer { flex: 1; }
  .br { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 6px; font: 12px ui-monospace, "SF Mono", Menlo, monospace; color: var(--ink-2); background: var(--raise); white-space: nowrap; }
  #zoom { font-size: 12.5px; color: var(--ink-3); font-variant-numeric: tabular-nums; min-width: 36px; text-align: right; }
  .menu { position: relative; }
  .menu .list { position: absolute; top: 38px; left: 0; min-width: 300px; background: var(--surface); border: 1px solid var(--line-2); border-radius: 10px; box-shadow: var(--pop); padding: 6px; display: none; z-index: 60; }
  .menu.open .list { display: block; }
  .pm { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; border-radius: 7px; text-align: left; font-size: 13.5px; color: var(--ink-2); }
  .pm span:first-child { flex: 1; white-space: nowrap; }
  .pm:hover, .pm.on { background: var(--raise); color: var(--ink); }
  .pm.sub { padding-left: 24px; color: var(--ink-3); font-size: 13px; }
  #view { position: fixed; inset: 52px 0 0 0; overflow: hidden; cursor: grab; background-color: var(--bg);
          background-image: radial-gradient(var(--line-2) 1px, transparent 1.2px); background-size: 28px 28px; }
  #view.drag { cursor: grabbing; }
  #world { position: absolute; top: 0; left: 0; transform-origin: 0 0; will-change: transform; }
  .board { position: absolute; }
  .board .frame { position: absolute; inset: 0; border-radius: 12px; overflow: hidden; background: var(--raise); border: 1px solid var(--line-2); box-shadow: var(--shadow); }
  .board iframe { border: 0; display: block; width: 100%; height: 100%; }
  /* The shield is why a drag that starts on a board still pans the canvas: an iframe would eat the
     pointer otherwise. A board that actually runs gives its pointer back on a second click. */
  .board .shield { position: absolute; inset: 0; z-index: 2; }
  .board.live .shield { pointer-events: none; }
  .board.sel .frame { box-shadow: 0 0 0 calc(2px * var(--inv, 1)) var(--accent), var(--shadow); border-color: transparent; }
  .board .won { position: absolute; left: 0; bottom: 0; z-index: 3; transform-origin: 0 100%; transform: scale(var(--inv, 1)); margin: 0; padding: 10px; }
  .board .won .chip { background: rgba(20,40,30,.88); color: #74c69d; }
  .board .pending { position: absolute; inset: 0; display: grid; place-items: center; color: var(--ink-3); font-size: 13px; }
  /* Labels counter-scale, so the overview still reads as a set of named screens when zoomed out. */
  .label { position: absolute; bottom: 100%; left: 0; margin-bottom: 9px; white-space: nowrap; transform-origin: 0 100%; transform: scale(var(--inv, 1));
           max-width: calc(var(--bw) * var(--k, 1) * 1px); overflow: hidden; text-overflow: ellipsis; font-size: 11.5px; letter-spacing: .09em; text-transform: uppercase; color: var(--ink-3); }
  .board.sel .label { color: var(--accent-text); }
  #world.tiny .label { display: none; }
  .label .runs { color: var(--accent-text); }
  .note { position: absolute; border-left: 2px solid rgba(var(--accent-rgb),.4); padding: 2px 0 2px 20px; }
  .note h3 { font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: var(--accent-text); margin: 0 0 11px; font-weight: 500; }
  .note p { margin: 0 0 11px; color: var(--ink-2); }
  #drawer { position: fixed; right: 0; top: 52px; bottom: 0; width: 400px; z-index: 40; background: var(--pane); border-left: 1px solid var(--line); padding: 22px 26px 30px; overflow-y: auto; box-shadow: -30px 0 60px -40px rgba(0,0,0,.6); display: none; }
  body.noted #drawer { display: block; }
  #drawer .dh { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  #drawer .dh button { margin-left: auto; color: var(--ink-3); display: flex; }
  #drawer .ttl { font-size: 17px; font-weight: 600; line-height: 1.35; letter-spacing: -.01em; margin: 0 0 12px; }
  #drawer .acts { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 12.5px; }
  #drawer .acts a { display: inline-flex; gap: 6px; align-items: center; color: var(--ink-3); }
  #drawer .acts a:hover { color: var(--ink); }
  #mini { position: fixed; left: 18px; bottom: 18px; width: 190px; height: 116px; z-index: 30; border-radius: 10px; background: var(--surface); border: 1px solid var(--line-2); box-shadow: var(--shadow); overflow: hidden; cursor: pointer; }
  #mini i { position: absolute; background: var(--raise); border-radius: 2px; }
  #mini i.w { background: rgba(var(--ok-rgb),.6); }
  #mini i.n { background: var(--line-2); }
  #mini b { position: absolute; border: 1.5px solid var(--accent); border-radius: 3px; }
  #help { position: fixed; right: 18px; bottom: 18px; z-index: 60; max-width: 330px; padding: 16px 18px; background: var(--surface); border: 1px solid var(--line-2); border-radius: 12px; font-size: 13px; color: var(--ink-2); display: none; box-shadow: var(--pop); }
  #help.on { display: block; }
  #help b { color: var(--ink); font-weight: 500; }
  #help div { margin: 5px 0; }
  @media (max-width: 900px) { #drawer { width: 100%; } .bar .chip, #zoom { display: none; } }
`, `
<div class="bar">
  <a class="home" href="/">${icon('back', 14)}All</a>
  <span class="name">${esc(c.name)}</span>${c.where ? `<span class="br" title="in ${esc(c.where.name)}">${esc(c.where.branch || 'detached')}</span>` : ''}
  ${pages.length > 1 ? `<span class="menu" id="menu"><button class="btn on" id="pagebtn"><span id="pagename">${esc(pg.name || '')}</span><span class="dim">${isRejected(pg) ? 'not chosen' : `${pages.filter((x) => !isRejected(x)).indexOf(pg) + 1} of ${pages.filter((x) => !isRejected(x)).length}`}</span>${icon('down', 14)}</button><div class="list">${pageMenu}</div></span>` : ''}
  <span id="dchip">${decisionChip(d, true)}</span>
  <span class="spacer"></span>
  <a class="btn" href="/?find=1" title="Search (&#8984;K)">${icon('search', 15)}<span class="kbd">&#8984;K</span></a>
  <span id="zoom"></span>
  <button class="btn" id="bfit">Fit</button>
  <a class="btn" id="bread" href="/read${esc(q({ d: c.dir, w: c.w, p: pg.id }))}">Read</a>
  <button class="btn" id="bnote">Note</button>
  ${THEME_SEG}
  <button class="btn" id="bhelp">?</button>
</div>
<div id="view"><div id="world"></div></div>
<aside id="drawer"><div class="dh"><span class="cap">The note beside it</span><button id="dclose" title="Close">${icon('x', 16)}</button></div><div id="dbody" class="prose"></div></aside>
<div id="mini"></div>
<div id="help">
  <div><b>drag</b> pan &middot; <b>&#8984;-scroll / pinch</b> zoom &middot; <b>scroll</b> pan</div>
  <div><b>f</b> fit everything &middot; <b>1</b> full size &middot; <b>+ &minus;</b> zoom</div>
  <div><b>click</b> a board for its note &middot; <b>double-click</b> to fill the screen with it</div>
  <div><b>click again</b> a board marked <span style="color:var(--accent-text)">runs</span> to use it &middot; <b>esc</b> hands it back</div>
  <div><b>[ ]</b> pages &middot; <b>n</b> the note &middot; <b>r</b> read it as a page &middot; <b>?</b> this</div>
</div>
<script>
${THEME_JS}
const DATA = ${JSON.stringify({ dir: c.dir, w: c.w || null, files: filesOf(c), canvas: c.canvas, notes, won })}
const BASE = DATA.files ? '/' + DATA.files + '/' : '/'
const view = document.getElementById('view'), world = document.getElementById('world')
const pages = ${JSON.stringify(pages.map((p) => ({ id: p.id ?? null, name: p.name ?? null, chip: (() => { const dd = isRejected(p) ? null : c.pages.find((x) => x.id === p.id)?.decision; return decisionChip(dd, true) })() })))}
let page = ${JSON.stringify(pg.id ?? null)}
let selected = ${JSON.stringify(start)}
const st = { k: 1, x: 0, y: 0 }
const items = []
const qs = o => '?' + Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&')
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const onPage = it => pages.length < 2 || (it.page ?? pages[0].id) === page
const drawerW = () => document.body.classList.contains('noted') && innerWidth > 900 ? 400 : 0

function build() {
  world.textContent = ''; items.length = 0
  for (const b of DATA.canvas.artboards || []) {
    if (!onPage(b)) continue
    const el = document.createElement('div')
    el.className = 'board' + (b.file === selected ? ' sel' : '')
    el.style.cssText = 'left:' + b.x + 'px; top:' + b.y + 'px; width:' + b.w + 'px; height:' + b.h + 'px; --bw:' + b.w
    el.innerHTML = '<div class="label">' + esc(b.title || b.file) + (b.is_interactive ? ' <span class="runs">&middot; runs</span>' : '') + '</div>' +
      '<div class="frame"><div class="pending">' + esc(b.file) + '</div></div><div class="shield"></div>' +
      (DATA.won[b.file] ? '<p class="won"><span class="chip"><i></i>Chosen</span></p>' : '')
    el.dataset.src = BASE + b.file; el.dataset.file = b.file; el.dataset.live = b.is_interactive ? '1' : ''
    world.append(el); items.push({ el, x: b.x, y: b.y, w: b.w, h: b.h, board: b })
  }
  for (const a of DATA.canvas.annotations || []) {
    if (!onPage(a)) continue
    const [head, ...rest] = String(a.text).split('\\n\\n')
    const el = document.createElement('div')
    el.className = 'note'
    el.style.cssText = 'left:' + a.x + 'px; top:' + a.y + 'px; width:' + a.w + 'px'
    el.innerHTML = '<h3>' + esc(head) + '</h3>' + rest.map(p => '<p>' + esc(p) + '</p>').join('')
    world.append(el); items.push({ el, x: a.x, y: a.y, w: a.w, h: 0 })
  }
  requestAnimationFrame(() => { for (const it of items) if (!it.board) it.h = it.el.offsetHeight; mini() })
  const p = pages.find(p => p.id === page)
  const pn = document.getElementById('pagename'); if (pn) pn.textContent = p?.name || ''
  document.querySelectorAll('.pm').forEach(b => b.classList.toggle('on', (b.dataset.page || null) === page))
  document.getElementById('dchip').innerHTML = p?.chip || ''
}

function bounds() {
  if (!items.length) return { x: 0, y: 0, w: 1440, h: 900 }
  const x0 = Math.min(...items.map(i => i.x)), y0 = Math.min(...items.map(i => i.y))
  const x1 = Math.max(...items.map(i => i.x + i.w)), y1 = Math.max(...items.map(i => i.y + (i.h || 200)))
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

function apply() {
  world.style.transform = 'translate(' + st.x + 'px, ' + st.y + 'px) scale(' + st.k + ')'
  world.style.setProperty('--inv', 1 / st.k)
  world.style.setProperty('--k', st.k)
  world.classList.toggle('tiny', st.k * 1440 < 150)
  document.getElementById('zoom').textContent = Math.round(st.k * 100) + '%'
  cull(); paintMini()
}

// A frame is only created once it is nearly in view -- and then kept, because a board that rebuilds
// itself every time you pan past it restarts its animations.
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
  const w = innerWidth - drawerW(), h = innerHeight - 52
  const k = Math.min((w - pad * 2) / b.w, (h - pad * 2) / b.h)
  st.k = Math.min(k, 2)
  st.x = (w - b.w * st.k) / 2 - b.x * st.k
  st.y = (h - b.h * st.k) / 2 - b.y * st.k
  apply()
}
const fit = () => frame(bounds())

// Open close enough to see the board that won, with the board drawn before it in the same row on
// the left, the way the canvas puts a direction beside Today.
function openOn(it) {
  const w = innerWidth - drawerW()
  st.k = Math.max(0.08, Math.min(1, (w - 80) / (it.w * 2.1)))
  const row = items.filter(o => o.board && o !== it && Math.abs(o.y - it.y) < it.h / 2 && o.x < it.x).sort((a, b) => b.x - a.x)[0]
  const left = row && (it.x + it.w - row.x) * st.k < w - 80 ? row.x : it.x
  st.x = 40 - left * st.k
  st.y = 70 - it.y * st.k
  apply()
}

function zoomAt(cx, cy, nk) {
  nk = Math.max(0.03, Math.min(4, nk))
  st.x = cx - (cx - st.x) * (nk / st.k); st.y = cy - (cy - st.y) * (nk / st.k); st.k = nk; apply()
}

function select(file, open) {
  selected = file
  items.forEach(it => it.board && it.el.classList.toggle('sel', it.board.file === file))
  const it = items.find(i => i.board && i.board.file === file)
  document.getElementById('bread').href = '/read' + qs({ d: DATA.dir, w: DATA.w, p: page, b: file })
  history.replaceState(null, '', '/canvas' + qs({ d: DATA.dir, w: DATA.w, p: page, b: file }))
  if (!it) return
  const body = DATA.notes[file]
  document.getElementById('dbody').innerHTML = '<p class="ttl">' + esc(it.board.title || file) + '</p>' + (body || '<p class="dim">No note sits beside this board.</p>') +
    '<div class="acts"><a href="/read' + qs({ d: DATA.dir, w: DATA.w, p: page, b: file }) + '">Read it in order</a><a href="' + esc(BASE + file) + '" target="_blank">Open alone</a><a href="/beside' + qs({ d: DATA.dir, w: DATA.w, b: file }) + '">Beside the panel</a></div>'
  if (open) setNote(true)
}
function setNote(on) {
  document.body.classList.toggle('noted', on)
  document.getElementById('bnote').classList.toggle('on', on)
}

// The minimap: everything on this page, and the part of it on screen.
let mb = null
function mini() {
  const el = document.getElementById('mini'), b = bounds(), pad = 8
  const k = Math.min((190 - pad * 2) / b.w, (116 - pad * 2) / b.h)
  mb = { b, k, ox: (190 - b.w * k) / 2, oy: (116 - b.h * k) / 2 }
  el.innerHTML = items.map(it => '<i class="' + (it.board ? (DATA.won[it.board.file] ? 'w' : '') : 'n') + '" style="left:' + (mb.ox + (it.x - b.x) * k).toFixed(1) + 'px;top:' + (mb.oy + (it.y - b.y) * k).toFixed(1) +
    'px;width:' + Math.max(2, it.w * k).toFixed(1) + 'px;height:' + Math.max(2, (it.h || 200) * k).toFixed(1) + 'px"></i>').join('') + '<b id="vp"></b>'
  paintMini()
}
function paintMini() {
  const vp = document.getElementById('vp'); if (!vp || !mb) return
  const x = (-st.x / st.k - mb.b.x) * mb.k + mb.ox, y = (-st.y / st.k - mb.b.y) * mb.k + mb.oy
  const w = (innerWidth - drawerW()) / st.k * mb.k, h = (innerHeight - 52) / st.k * mb.k
  const cx = Math.max(0, x), cy = Math.max(0, y)
  vp.style.cssText = 'left:' + cx + 'px;top:' + cy + 'px;width:' + Math.max(4, Math.min(190, x + w) - cx) + 'px;height:' + Math.max(4, Math.min(116, y + h) - cy) + 'px'
}
document.getElementById('mini').onclick = e => {
  const r = e.currentTarget.getBoundingClientRect()
  const wx = (e.clientX - r.left - mb.ox) / mb.k + mb.b.x, wy = (e.clientY - r.top - mb.oy) / mb.k + mb.b.y
  st.x = (innerWidth - drawerW()) / 2 - wx * st.k; st.y = (innerHeight - 52) / 2 - wy * st.k; apply()
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
  // A click that did not turn into a drag picks the board and opens its note; on a board already
  // picked that runs, it hands the board its pointer.
  const board = d.t.closest('.board')
  if (!board) return
  if (board.dataset.file === selected && board.dataset.live) board.classList.add('live')
  else select(board.dataset.file, true)
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

function goPage(id) {
  page = id; selected = null; build()
  requestAnimationFrame(() => { fit(); history.replaceState(null, '', '/canvas' + qs({ d: DATA.dir, w: DATA.w, p: page })) })
  document.getElementById('bread').href = '/read' + qs({ d: DATA.dir, w: DATA.w, p: page })
}
addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); location = '/?find=1'; return }
  if (e.metaKey || e.ctrlKey) return
  const c = (innerWidth - drawerW()) / 2, m = (innerHeight - 52) / 2
  if (e.key === 'f') fit()
  else if (e.key === '1') zoomAt(c, m, 1)
  else if (e.key === '+' || e.key === '=') zoomAt(c, m, st.k * 1.25)
  else if (e.key === '-') zoomAt(c, m, st.k / 1.25)
  else if (e.key === 'Escape') { document.querySelectorAll('.board.live').forEach(b => b.classList.remove('live')); document.getElementById('menu')?.classList.remove('open') }
  else if (e.key === 'n') { setNote(!document.body.classList.contains('noted')); paintMini() }
  else if (e.key === 'r') location = document.getElementById('bread').href
  else if (e.key === '?') document.getElementById('help').classList.toggle('on')
  else if (e.key === '[' || e.key === ']') {
    const i = pages.findIndex(p => p.id === page)
    const n = pages[(i + (e.key === ']' ? 1 : pages.length - 1)) % pages.length]
    if (n && n.id !== page) goPage(n.id)
  }
})
const menu = document.getElementById('menu')
if (menu) {
  document.getElementById('pagebtn').onclick = e => { e.stopPropagation(); menu.classList.toggle('open') }
  menu.querySelectorAll('.pm').forEach(b => b.onclick = () => { menu.classList.remove('open'); goPage(b.dataset.page || null) })
  addEventListener('click', e => { if (!menu.contains(e.target)) menu.classList.remove('open') })
}
document.getElementById('bfit').onclick = fit
document.getElementById('bnote').onclick = () => { setNote(!document.body.classList.contains('noted')); paintMini() }
document.getElementById('dclose').onclick = () => { setNote(false); paintMini() }
document.getElementById('bhelp').onclick = () => document.getElementById('help').classList.toggle('on')
addEventListener('resize', () => { cull(); paintMini() })

build()
requestAnimationFrame(() => {
  const it = selected && items.find(i => i.board && i.board.file === selected)
  if (it) { select(selected, true); openOn(it) } else fit()
})
</script>`)
}

// ---- beside -------------------------------------------------------------------------------------
// A board and the panel it became, side by side at the same size: the comparison AGENTS.md asks for
// when a screen is built. The panel is whatever address is in the field, the dev server by default.

export function besidePage(c, b) {
  return page(`${b.title || b.file} — beside the panel`, `
  .bar { height: 56px; display: flex; align-items: center; gap: 14px; padding: 0 18px; border-bottom: 1px solid var(--line); }
  .bar .t { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .bar .search { width: 320px; margin-left: auto; height: 34px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; padding: 24px; }
  .two figure { margin: 0; }
  .two figcaption { font-size: 12.5px; color: var(--ink-3); margin-bottom: 8px; }
  .hold { position: relative; overflow: hidden; border-radius: 10px; border: 1px solid var(--line-2); background: var(--raise); }
  .hold iframe { position: absolute; left: 0; top: 0; border: 0; transform-origin: 0 0; }
`, `
<div class="bar"><a class="dim" href="/read${esc(q({ d: c.dir, w: c.w, b: b.file }))}">${icon('back', 14)}</a><span class="t">${esc(b.title || b.file)}</span>
  <label class="search">${icon('page', 15)}<input id="url" spellcheck="false" placeholder="The panel's address"></label>${THEME_SEG}</div>
<div class="two">
  <figure><figcaption>The board &middot; ${b.w} &times; ${b.h}</figcaption><div class="hold"><iframe src="/${esc((filesOf(c) ? filesOf(c) + '/' : '') + b.file)}" width="${b.w}" height="${b.h}" scrolling="no"></iframe></div></figure>
  <figure><figcaption id="pcap">The panel</figcaption><div class="hold"><iframe id="panel" width="${b.w}" height="${b.h}"></iframe></div></figure>
</div>
<script>
${THEME_JS}
const url = document.getElementById('url'), panel = document.getElementById('panel')
let saved = 'http://localhost:5173/'
try { saved = localStorage.getItem('artboards-panel') || saved } catch (e) {}
url.value = saved
function load() { panel.src = url.value; document.getElementById('pcap').textContent = 'The panel \\u00b7 ' + url.value; try { localStorage.setItem('artboards-panel', url.value) } catch (e) {} }
url.onkeydown = e => { if (e.key === 'Enter') load() }
function fit() {
  document.querySelectorAll('.hold').forEach(h => {
    const f = h.querySelector('iframe'), k = Math.min(1, h.parentElement.clientWidth / f.width)
    f.style.transform = 'scale(' + k + ')'; h.style.height = (f.height * k) + 'px'
  })
}
addEventListener('resize', fit); fit(); load()
</script>`)
}
