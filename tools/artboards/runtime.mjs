// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The runtime the boards were drawn against.
//
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
import { readFile } from 'node:fs/promises'
import path from 'node:path'

let supportCache
export async function supportJs(DESIGN) {
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
