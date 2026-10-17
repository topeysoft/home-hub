/* hub.elyir.com is design/site's D: A's front page with C's line for a hub ready to plug in. These fail on purpose if the
   page drifts from the board, if /install could ever hand bash a web page, or if the waitlist says more than it should.
   `node --test site/site.test.mjs` */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { onRequest as install } from './functions/install.js'
import { onRequestPost as waitlist } from './functions/waitlist.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const page = readFileSync(path.join(HERE, 'index.html'), 'utf8')
const text = (html) => html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')
const at = (s) => { const i = page.indexOf(s); assert.notEqual(i, -1, `the page should have ${s}`); return i }

test('the top is D: what it is, the computer first, then Try it live, then the line for one ready to plug in', () => {
  const hero = page.slice(at('<header class="hero">'), at('</header>'))
  assert.match(hero, /<h1>Your house, on one screen\.<\/h1>/)
  const computer = hero.indexOf('Put it on a computer you have'), live = hero.indexOf('Try it live'), ask = hero.indexOf('Want one ready to plug in?')
  assert.ok(computer > 0 && computer < live && live < ask, 'the two buttons, then the line under them')
  assert.match(hero, /class="pill lamp door-get"/, 'on a computer, the computer is the lit button')
  assert.equal((hero.match(/class="pill lamp/g) || []).length, 1, "one lit button at the top; the line's Tell me stays plain")
  assert.match(hero, /type="email"/)
})

test('on a phone, Try it live leads, because the command needs a computer', () => {
  const phone = page.slice(at('@media (max-width: 640px)'))
  assert.match(phone.slice(0, phone.indexOf('\n  }')), /\.doors \.door-try \{ order: -1; background: var\(--lamp\)/)
})

test('below the top: the pretend house, the three ways to get it, then the price', () => {
  const order = ['id="try"', 'id="get"', 'id="anywhere"', '<footer>'].map(at)
  assert.deepEqual(order, [...order].sort((a, b) => a - b))
  const ways = [...page.slice(at('id="get"'), at('id="anywhere"')).matchAll(/<h3>(.*?)<\/h3>/g)].map((m) => m[1])
  assert.deepEqual(ways, ['On a computer you have', 'On a new Raspberry Pi 5', 'Ready to plug in'])
  assert.match(text(page), /Free at home\. \$3 a month to use it anywhere\./)
})

test("the command is the site's own, and the pretend house says it isn't built yet", () => {
  assert.match(page, /curl -fsSL https:\/\/hub\.elyir\.com\/install \| sudo bash/)
  assert.match(text(page.slice(at('id="try"'), at('id="get"'))), /Coming soon/)
})

test("the page shows nobody else's show or brand, and names Home Assistant once", () => {
  for (const name of ['The Bear', 'Disney', 'Philips', 'Hue', 'Sonos', 'Chromecast', 'Miles Davis', 'Blue in Green']) {
    assert.ok(!page.includes(name), `the page says ${name}`)
  }
  assert.equal((text(page).match(/Home Assistant/g) || []).length, 2, 'once in the footer, and once in the line that says it is a trademark')
  for (const word of ['relay', 'brain', 'driver', 'entity', 'integration']) assert.ok(!new RegExp(`\\b${word}`, 'i').test(text(page)), `the page says ${word}`)
})

const assets = { fetch: async (req) => new Response('#!/usr/bin/env bash\necho hub\n', { status: 200, headers: { 'Content-Type': 'application/x-sh', from: new URL(req.url).pathname } }) }
const get = (accept) => install({ request: new Request('https://hub.elyir.com/install', { headers: accept ? { Accept: accept } : {} }), env: { ASSETS: assets } })

test('/install gives curl the script, as plain text', async () => {
  for (const accept of [undefined, '*/*', 'text/plain']) {
    const res = await get(accept)
    assert.equal(res.status, 200)
    assert.equal(res.headers.get('from'), '/install.sh')
    assert.equal(res.headers.get('Content-Type'), 'text/plain; charset=utf-8')
    assert.match(await res.text(), /^#!/)
  }
})

test('/install sends a browser to the ways to get it, never a page to bash', async () => {
  const res = await get('text/html,application/xhtml+xml')
  assert.equal(res.status, 302)
  assert.equal(res.headers.get('Location'), '/#get')
})

function list() {
  const rows = new Map()
  return {
    rows,
    prepare: (sql) => ({
      run: async () => ({}),
      bind: (...args) => ({ run: async () => { if (/INSERT/.test(sql)) { const k = `${args[0]}|${args[1]}`; if (!rows.has(k)) rows.set(k, args[2]) } return {} } }),
    }),
  }
}
const ask = (body, env) => waitlist({ request: new Request('https://hub.elyir.com/waitlist', { method: 'POST', body: typeof body === 'string' ? body : JSON.stringify(body) }), env })

test('the waitlist keeps one email for the hub, and says the same thing the second time', async () => {
  const db = list()
  assert.equal((await ask({ email: ' Sam@Example.com ' }, { WAITLIST: db })).status, 200)
  assert.equal((await ask({ email: 'sam@example.com' }, { WAITLIST: db })).status, 200)
  assert.deepEqual([...db.rows.keys()], ['sam@example.com|hub'])
})

test("the waitlist turns away what isn't an email, and quietly ignores a script", async () => {
  const db = list()
  for (const bad of [{ email: 'sam' }, { email: 'sam@example' }, { email: `${'a'.repeat(250)}@example.com` }, {}]) {
    assert.equal((await ask(bad, { WAITLIST: db })).status, 400)
  }
  assert.equal((await ask('not json', { WAITLIST: db })).status, 400)
  assert.equal((await ask({ email: 'bot@example.com', website: 'http://spam' }, { WAITLIST: db })).status, 200)
  assert.equal(db.rows.size, 0)
})

test('the waitlist says plainly when it has nowhere to write', async () => {
  assert.equal((await ask({ email: 'sam@example.com' }, {})).status, 503)
})

test('a visit asks nobody else for anything: no fonts, scripts or pictures from another site', () => {
  const fetched = [...page.matchAll(/<(?:link|script|img|iframe)\b[^>]*\b(?:href|src)="([^"]+)"/g)].map((m) => m[1])
  assert.ok(fetched.length > 0)
  for (const url of fetched) assert.ok(url.startsWith('/'), `the page loads ${url}`)
  assert.ok(!/url\(['"]?https?:/.test(page), 'nor from a stylesheet')
})

test('the privacy page is reachable from the waitlist, and says what it keeps', () => {
  const ways = page.slice(at('id="get"'), at('id="anywhere"'))
  assert.match(ways, /href="\/privacy"/)
  assert.match(page.slice(at('<footer>')), /href="\/privacy"/)
  const privacy = text(readFileSync(path.join(HERE, 'privacy.html'), 'utf8'))
  assert.match(privacy, /your email address, that it was for the hub, and when you joined/)
  assert.match(privacy, /privacy@elyir\.app/)
  for (const word of ['relay', 'brain', 'entity', 'integration']) assert.ok(!new RegExp(`\\b${word}`, 'i').test(privacy), `the privacy page says ${word}`)
})
