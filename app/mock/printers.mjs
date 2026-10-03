/* The house's 3D printers, for the mock brain (brain/hub/printers.py, docs/printers.md, design/printers/).

   A house with printers is a different house -- a print card leads Your afternoon, the band has R2D2's
   line in it -- and every other board and test was drawn at the house without them. So they are there
   only when the PAGE asks: `?printers=` on the panel's own address, read off each request's Referer, or
   PRINTERS=<scenario> for the whole mock. One mock serves every e2e test at once, so a page that asks
   gets its own copy of the scenario, keyed by its address, and what it changes (a room, an ask) is its own.

     ?printers=1 | printing   OBI1 printing a phone stand, R2D2 stopped with nothing on its bed, C3PO ready
     ?printers=needs_you      OBI1 waiting for a spool, with its two answers
     ?printers=finished       OBI1 done, cooling
     ?printers=room           as printing, with OBI1 and C3PO in the Office (the boards' Workshop)
     ?printers=found          no printers yet, three on the Wi-Fi
     ?printers=asking         ...and the hub asking OBI1, 1:42 left
     ?printers=answers        ...and the four answers, in the rows that asked

   Every value is the boards': 42%, layer 118 of 280, done at 4:20 PM against the ?at=14:47 clock, white PLA,
   220/60/38. The camera is a drawing of the bed, not a stream; ?still=1 or not, the same picture. */

const HOME = id => `https://192-168-86-7${id.length}.${id}.home.elyir.app`
const AWAY = id => `https://${id}.elyir.app`
const NAMES = { obi1: 'OBI1', r2d2: 'R2D2', c3po: 'C3PO' }
const WORDS = { ready: 'ready', preparing: 'getting ready', printing: 'printing', needs_you: 'needs you', finished: 'done', problem: 'stopped' }
const ROOMS = { living: 'Living room', kitchen: 'Kitchen', bedroom: 'Bedroom', office: 'Office', front: 'Front door', garage: 'Garage', backyard: 'Backyard', bath: 'Bathroom' }

/* What the page asked for, and the clock it is showing: ?at=14:47 means the print is done at 4:20 PM on
   that clock, the way the board says, rather than an hour and a half after whenever the test ran. */
function asked(req) {
  let q = new URLSearchParams()
  try { q = new URL(req.headers.referer || '').searchParams } catch { /* no page behind it: a curl, a test */ }
  const scenario = q.get('printers') ?? process.env.PRINTERS ?? null
  const at = q.get('at')
  const now = new Date()
  if (at) { const [h, m] = at.split(':').map(Number); now.setHours(h || 0, m || 0, 0, 0) }
  return { scenario: scenario === '1' ? 'printing' : scenario, key: q.toString(), now: now.getTime() / 1000 }
}

const PLA = { colors: ['#f4f1ea'], material: 'PLA', filament: 'White PLA' }
function obi1(state, now) {
  const job = { name: 'Phone stand', progress: 0.42, layer: 118, layers: 280, remaining_s: 5580, eta_clock: '4:20 pm',
                elapsed_s: 7440, ...PLA, thumbnail: '/printers/obi1/thumbnail' }
  if (state === 'needs_you') return { state, headline: 'OBI1 needs you', since: now - 240,
    detail: 'White PLA ran out. Load a new spool into slot 2, or let me switch to the white in slot 6.',
    actions: [{ id: 'swap_slot', label: 'Switch to slot 6', primary: true, style: 'amber', args: { slot: 5 } }, { id: 'resume', label: 'Resume' }],
    temps: { nozzle: 220, bed: 60, chamber: 38 }, job }
  if (state === 'finished') return { state, headline: 'OBI1: Phone stand is done', since: now - 29 * 60,
    detail: 'I’ll tell you when the bed is cool enough to lift it off.', actions: [],
    temps: { nozzle: 41, bed: 52, chamber: 36 }, job: { ...job, progress: 1, layer: 280, remaining_s: 0, elapsed_s: 13020 } }
  if (state === 'paused') return { state: 'needs_you', headline: 'Paused.', since: now,
    detail: 'The print is waiting for you. Everything is warm and safe.',
    actions: [{ id: 'resume', label: 'Carry on', primary: true, style: 'amber' }, { id: 'cancel', label: 'Stop this print' }],
    temps: { nozzle: 220, bed: 60, chamber: 38 }, job }
  if (state === 'stopped') return { state: 'ready', headline: 'Print stopped.', since: now,
    detail: 'Clear the bed when you’re ready. Nothing else to do.', actions: [], temps: { nozzle: 180, bed: 58, chamber: 37 }, job: null }
  return { state: 'printing', headline: 'Phone stand', detail: 'Done at about 4:20 pm', since: now - 7440,
    actions: [{ id: 'pause', label: 'Pause' }, { id: 'cancel', label: 'Stop this print' }],
    temps: { nozzle: 220, bed: 60, chamber: 38 }, job }
}
const R2D2 = now => ({ state: 'problem', headline: 'R2D2 stopped', since: now - 5700,
  detail: 'The toolhead isn’t answering. Check the cable to the head, then try again.',
  actions: [{ id: 'help', label: 'Show me what to check' }], temps: { nozzle: 24, bed: 23 }, job: null })
const C3PO = () => ({ state: 'ready', headline: 'Ready', detail: 'No spools loaded yet.', since: null, actions: [], temps: { nozzle: 26, bed: 25 }, job: null })

function printer(id, live, room = null) {
  return { id, name: NAMES[id], connected: true, via: 'home', word: WORDS[live.state] ?? '', camera: `/printers/${id}/camera`,
           room: room ? { id: room, name: ROOMS[room] ?? room } : null, ...live }
}
const found = id => ({ id, name: NAMES[id], home: HOME(id), away: AWAY(id), kind: '3D printer' })

function seed(scenario, now) {
  const printing = () => ({ printers: [printer('c3po', C3PO()), printer('obi1', obi1('printing', now)), printer('r2d2', R2D2(now))], found: [], asking: {}, until: {} })
  if (scenario === 'needs_you') return { ...printing(), printers: [printer('c3po', C3PO()), printer('obi1', obi1('needs_you', now))] }
  if (scenario === 'finished') return { ...printing(), printers: [printer('c3po', C3PO()), printer('obi1', obi1('finished', now))] }
  if (scenario === 'room') return { ...printing(), printers: [printer('c3po', C3PO(), 'office'), printer('obi1', obi1('printing', now), 'office'), printer('r2d2', R2D2(now))] }
  if (scenario === 'found') return { printers: [], found: ['obi1', 'r2d2', 'c3po'].map(found), asking: {}, until: {} }
  if (scenario === 'asking') return { printers: [], found: ['obi1', 'r2d2', 'c3po'].map(found), asking: { obi1: 'waiting' }, until: { obi1: Date.now() / 1000 + 102 } }
  if (scenario === 'answers') return { printers: [printer('obi1', obi1('printing', now))], found: ['r2d2', 'c3po'].map(found),
    asking: { obi1: 'allowed', r2d2: 'refused', c3po: 'expired' }, until: {} }
  return printing()
}

const houses = new Map()
function house(req) {
  const a = asked(req)
  if (!a.scenario) return null
  if (!houses.has(a.key)) houses.set(a.key, { ...seed(a.scenario, a.now), now: a.now })
  return houses.get(a.key)
}

/* The brain's words for each ask (Printers.ask_words), copied: the row on Add says them as they are. */
function askWords(h, id) {
  const state = h.asking[id], name = NAMES[id]
  const words = {
    waiting: [`Tap Allow on ${name}’s screen`, `Or on a phone that already has ${name}, if it’s at home.`],
    allowed: [`${name} is in the house`, ''],
    refused: [`${name} said no`, `Somebody tapped Not now on ${name}’s screen.`],
    expired: [`Nobody answered on ${name}`, `An ask lasts two minutes. Ask again, then tap Allow on ${name}’s screen.`],
    failed: [`Couldn’t reach ${name}`, 'It’s on the Wi‑Fi but didn’t answer. Check it’s switched on, then ask again.'],
  }[state] ?? [name, '']
  const p = h.printers.find(x => x.id === id)
  if (state === 'allowed' && p) words[1] = p.state === 'printing' && p.job ? `Printing ${p.job.name}, ${Math.round(p.job.progress * 100)}%.` : `${p.word[0].toUpperCase()}${p.word.slice(1)}.`
  return { id, name, state, title: words[0], detail: words[1], until: state === 'waiting' ? h.until[id] ?? null : null }
}
const status = h => ({ printers: h.printers, found: h.found.filter(f => !h.printers.some(p => p.id === f.id)), asking: h.asking,
                       asks: Object.keys(h.asking).map(id => askWords(h, id)) })

/** Needs a look's rows for a house with printers, in the brain's shape (Printers.notes). */
export function printerNotes(req) {
  const h = house(req)
  if (!h) return []
  return h.printers.filter(p => p.state === 'needs_you' || p.state === 'problem').map(p => ({
    kind: 'printer', subject: p.id, since: p.since, name: p.name, text: p.headline, more: p.detail,
    where: [p.room?.name, 'a 3D printer'].filter(Boolean).join(' · '), acts: [{ do: `Open ${p.name}`, act: 'printer', to: p.id }] }))
}
/** A page looking at printers is looking at the boards' house, which had nothing else found nearby. */
export const printersAsked = req => !!house(req)

function send(res, body, code = 200) { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)) }
function read(req, then) { let raw = ''; req.on('data', c => (raw += c)); req.on('end', () => { let b = {}; try { b = JSON.parse(raw) } catch { /* empty */ } then(b) }) }

/* The camera: OBI1's bed, as the boards draw it -- the gantry, the nozzle's glow, the part half made. */
const BED = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" width="640" height="360">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a2e35"/><stop offset=".62" stop-color="#16181c"/><stop offset="1" stop-color="#0c0d10"/></linearGradient>
<linearGradient id="p" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6e5a3a"/><stop offset="1" stop-color="#3e3322"/></linearGradient>
<pattern id="d" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".9" fill="rgba(255,230,180,.16)"/></pattern>
<radialGradient id="v" cx=".5" cy=".45" r=".75"><stop offset=".55" stop-color="rgba(0,0,0,0)"/><stop offset="1" stop-color="rgba(0,0,0,.6)"/></radialGradient>
<filter id="b"><feGaussianBlur stdDeviation="4"/></filter></defs>
<rect width="640" height="360" fill="url(#g)"/><ellipse cx="320" cy="-6" rx="320" ry="70" fill="rgba(255,244,226,.13)"/>
<g transform="translate(0 -14)"><rect x="40" y="-60" width="20" height="330" fill="#121418"/><rect x="580" y="-60" width="20" height="330" fill="#121418"/>
<polygon points="76,246 564,246 660,420 -20,420" fill="url(#p)"/><polygon points="76,246 564,246 660,420 -20,420" fill="url(#d)"/>
<ellipse cx="330" cy="304" rx="96" ry="9" fill="rgba(0,0,0,.4)"/>
<polygon points="250,302 410,302 410,284 250,284" fill="#e9e5dc"/><polygon points="250,284 410,284 401,276 259,276" fill="#f7f4ee"/>
<polygon points="258,284 272,284 272,262 258,262" fill="#efebe3"/><polygon points="352,284 380,284 386,236 362,236" fill="#ece8e0"/>
<rect x="30" y="168.5" width="580" height="15" rx="3" fill="#2c3037"/><rect x="336" y="160.5" width="72" height="62" rx="7" fill="#1c1f25"/>
<circle cx="372" cy="190.5" r="17" fill="#15171c" stroke="rgba(255,255,255,.09)" stroke-width="1.5"/><circle cx="372" cy="190.5" r="4.5" fill="#262a31"/>
<rect x="360" y="222.5" width="24" height="8" fill="#2a2d33"/><polygon points="366,230.5 378,230.5 374,234.5 370,234.5" fill="#c9a24a"/>
<circle cx="372" cy="235.5" r="9" fill="rgba(255,150,60,.55)" filter="url(#b)"/></g><rect width="640" height="360" fill="url(#v)"/></svg>`
const PART = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="236 130 190 190" width="300" height="300">
<polygon points="250,302 410,302 410,284 250,284" fill="#e9e5dc"/><polygon points="250,284 410,284 401,276 259,276" fill="#f7f4ee"/>
<polygon points="258,284 272,284 272,262 258,262" fill="#efebe3"/><polygon points="352,284 380,284 398,150 372,150" fill="#ece8e0"/>
<polygon points="380,284 392,279 410,146 398,150" fill="#cfcac0"/></svg>`

/** Every /printers route. Returns false when the page did not ask for printers and this is not one. */
export function printersRoute(req, res, p) {
  if (!p.startsWith('/printers')) return false
  const h = house(req)
  const m = p.match(/^\/printers\/([^/]+)(?:\/([^/]+))?$/)
  if (m && (m[2] === 'camera' || m[2] === 'thumbnail')) {
    res.writeHead(200, { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'no-store' })
    res.end(m[2] === 'camera' ? BED : PART)
    return true
  }
  /* A house without printers is a hub that has them and none in yet -- what a fresh brain answers. */
  if (!h) { send(res, { printers: [], found: [], asking: {}, asks: [] }); return true }
  if (p === '/printers' || p === '/printers/look') { send(res, status(h)); return true }
  const id = m?.[1], what = m?.[2]
  const one = h.printers.find(x => x.id === id)
  if (what === 'add' && req.method === 'POST') {
    if (!h.found.some(f => f.id === id)) { send(res, { detail: 'That printer isn’t on the Wi‑Fi.' }, 404); return true }
    h.asking[id] = 'waiting'; h.until[id] = Date.now() / 1000 + 120
    /* Somebody at the printer taps Allow a few seconds later. A test that wants a no says so in its name. */
    setTimeout(() => {
      if (h.asking[id] !== 'waiting') return
      h.asking[id] = 'allowed'
      h.printers.push(printer(id, id === 'obi1' ? obi1('printing', h.now) : C3PO()))
    }, Number(process.env.PRINTER_ALLOWS_AFTER || 2500))
    send(res, status(h)); return true
  }
  if (what === 'add' && req.method === 'DELETE') { if (h.asking[id] === 'waiting') delete h.asking[id]; send(res, status(h)); return true }
  if (!one) { send(res, { detail: 'No printer by that name.' }, 404); return true }
  if (what === 'room') {
    read(req, b => {
      if (b.room && !(b.room in ROOMS)) return send(res, { detail: 'There’s no room by that name.' }, 400)
      one.room = b.room ? { id: b.room, name: ROOMS[b.room] } : null
      send(res, one)
    })
    return true
  }
  if (what === 'action') {
    read(req, b => {
      const next = b.action === 'pause' ? 'paused' : b.action === 'cancel' ? 'stopped' : b.action === 'resume' || b.action === 'swap_slot' ? 'printing' : null
      if (!next) return send(res, one)
      Object.assign(one, obi1(next, h.now), { word: WORDS[obi1(next, h.now).state] })
      send(res, one)
    })
    return true
  }
  if (!what && req.method === 'DELETE') { h.printers = h.printers.filter(x => x.id !== id); send(res, status(h)); return true }
  send(res, one)
  return true
}
