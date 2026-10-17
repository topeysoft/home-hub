#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Every design artboard in a browser: found, read, and laid out the way canvas.json says.
//
//   tools/dev.sh design            the contents of design/, opened in a browser
//   node tools/artboards.mjs       the same thing without the wrapper
//   node tools/artboards.mjs --port 8410 --no-open
//   node tools/artboards.mjs --design ../home-hub-a/design --port 8416
//
// The boards were drawn on a canvas -- canvas.json carries an x, a y and a width for every board AND
// for every note, which is the argument for the board sitting next to it. Open a .dc.html on its own
// and all of that is gone: one screen, no neighbors, no note saying why it is that way.
//
// So nothing is generated to disk here. The server reads canvas.json on every request and draws it
// four ways, as design/artboards/ drew them and as was chosen there on 5 October 2026:
//
//   /          the contents: every collection one line, newest first, grouped by area, with what was
//              decided on it; the search field at the top narrows the same page (/search answers it)
//   /read      one page of a collection as a document: the decision, then each board with its note
//   /canvas    the canvas, opening on the board that won, with the note of whichever board you click
//   /beside    a board next to the panel it became, at the same size
//   /w/<checkout>/...   a file from another worktree's design/, for a collection drawn there and not
//              merged here yet -- the front page lists those under From other checkouts
//
// What is known about a collection is worked out in artboards/lib.mjs, apart from any HTML, and held
// to the boards by artboards/lib.test.mjs. The pages are artboards/pages.mjs.
//
// No dependencies, and no build. Node's own http is all of it, which matters because looking at the
// screens is the one thing in this checkout that is supposed to need nothing installed.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { allCollections, collectionDirs, elsewhere, search, worktrees } from './artboards/lib.mjs'
import { contentsPage, documentPage, canvasPage, besidePage } from './artboards/pages.mjs'
import { supportJs } from './artboards/runtime.mjs'

const argv = process.argv.slice(2)
const arg = (name, fallback) => { const i = argv.indexOf(name); return i === -1 ? fallback : argv[i + 1] }

// --design points the viewer at another checkout's boards: a session in another worktree draws a
// collection there, and it is looked at there, before either branch has the other's work.
const HERE = path.dirname(fileURLToPath(import.meta.url))
const DESIGN = path.resolve(arg('--design', path.join(HERE, '..', 'design')))
const PORT = Number(arg('--port', process.env.PORT || 8402))
const OPEN = !argv.includes('--no-open')

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.mp4': 'video/mp4', '.webm': 'video/webm' }

const send = (res, code, type, body) =>
  res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' }).end(body)

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x')
  const p = url.searchParams
  const dir = p.get('d') || ''
  try {
    if (url.pathname === '/') {
      const here = await allCollections(DESIGN)
      return send(res, 200, TYPES['.html'], contentsPage(here, p.get('q') || '', await elsewhere(DESIGN, here)))
    }
    if (url.pathname === '/search') {
      const here = await allCollections(DESIGN)
      return send(res, 200, TYPES['.json'], JSON.stringify(search([...here, ...await elsewhere(DESIGN, here)], p.get('q') || '')))
    }
    if (['/read', '/canvas', '/beside'].includes(url.pathname)) {
      if (dir.includes('..') || path.isAbsolute(dir)) return send(res, 400, 'text/plain', 'no')
      const here = await allCollections(DESIGN)
      const w = p.get('w')
      const c = w ? (await elsewhere(DESIGN, here)).find((x) => x.w === w && x.dir === dir) : here.find((x) => x.dir === dir)
      if (!c) return send(res, 404, 'text/plain', w ? `nothing new in design/${dir} in ${w}` : `no collection design/${dir}`)
      const page = p.has('p') ? (p.get('p') || null) : undefined
      if (url.pathname === '/read') return send(res, 200, TYPES['.html'], documentPage(c, page, p.get('b'), c.year))
      if (url.pathname === '/canvas') return send(res, 200, TYPES['.html'], canvasPage(c, page, p.get('b'), c.year))
      const b = (c.canvas.artboards || []).find((x) => x.file === p.get('b'))
      return b ? send(res, 200, TYPES['.html'], besidePage(c, b)) : send(res, 404, 'text/plain', 'no such board')
    }
    // Ninety-two of the ninety-three boards open with <script src="./support.js">, and no such
    // file has ever been in this checkout -- see artboards/runtime.mjs for where it is found instead.
    if (url.pathname.endsWith('/support.js')) {
      const js = await supportJs(DESIGN)
      return send(res, js === null ? 404 : 200, TYPES['.js'], js ?? 'no dc-runtime found')
    }
    // A file in another checkout's design/, under that checkout's folder name: /w/home-hub-a/bridge-light/HubA.dc.html.
    const away = url.pathname.match(/^\/w\/([^/]+)\/(.+)$/)
    if (away && !away[2].endsWith('support.js')) {
      const wt = (await worktrees(DESIGN)).find((x) => x.name === decodeURIComponent(away[1]))
      if (!wt) return send(res, 404, 'text/plain', 'no such checkout')
      const base = path.join(wt.path, 'design')
      const file = path.join(base, decodeURIComponent(away[2]))
      if (!file.startsWith(base + path.sep)) return send(res, 403, 'text/plain', 'outside design/')
      return send(res, 200, TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', await readFile(file))
    }
    // Everything else is a file in design/, at the path it really has -- which is what keeps the
    // relative links inside the boards, and the hand-written index.html pages, working.
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
  const n = (await collectionDirs(DESIGN)).length
  console.log(`${n} collections of boards at ${at}   (ctrl-c to stop)`)
  if (OPEN) spawn(process.platform === 'darwin' ? 'open' : 'xdg-open', [at], { stdio: 'ignore' }).unref()
})
