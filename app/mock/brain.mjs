/* A stand-in for the brain, for looking at the panel without a hub: serves ../dist and enough JSON for a lived-in
   house of eight rooms. `npm run mock`, then open http://localhost:8399/ (every ?at= ?wx= ?month= ?room= ?sheet= ?setup=
   preview works), or `BRAIN=http://localhost:8399 npm run dev` for hot reload against it.
   Knobs: PORT, WX=rainy (a condition), FOUND=0 (nothing new nearby), ENGINE=down (the engine-starting screen),
   LOCKED=1 (a code is set), FRESH=1 (first run). Nothing here talks to a real device; every POST says ok. */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const PORT = Number(process.env.PORT || 8399)
const now = Math.floor(Date.now() / 1000)

const dev = (id, name, room_id, capability, state, attrs = {}) => ({ id, name, room_id, capability, state, attrs })
const rooms = [
  { id: 'living', name: 'Living room', intent: 'movie', set_by: 'rule:evening-lights', hold_until: null, devices: [
    dev('l1', 'Ceiling light', 'living', 'light', 'on', { brightness: 90, supported_color_modes: ['brightness'] }),
    dev('l2', 'Floor lamp', 'living', 'light', 'on', { brightness: 60, supported_color_modes: ['brightness'] }),
    dev('l3', 'Reading lamp', 'living', 'light', 'off', { supported_color_modes: ['onoff'] }),
    dev('m1', 'Living room TV', 'living', 'media', 'playing', { media_title: 'The Bear', media_artist: 'Season 3, Episode 4', app_name: 'Disney+', volume_level: 0.35, entity_picture: '/x.jpg' }),
    dev('s1', 'Sonos', 'living', 'media', 'paused', { media_title: 'Blue in Green', media_artist: 'Miles Davis', volume_level: 0.2 }),
    dev('c1', 'Blinds', 'living', 'cover', 'open', { current_position: 70 }),
    dev('t1', 'Thermostat', 'living', 'climate', 'cool', { current_temperature: 74, temperature: 71, hvac_action: 'cooling', hvac_modes: ['heat', 'cool', 'heat_cool', 'off'], fan_modes: ['on', 'auto'], fan_mode: 'auto', current_humidity: 48 }),
    dev('mo1', 'Motion', 'living', 'motion', 'on', {}),
    dev('te1', 'Temperature', 'living', 'sensor.temperature', '73.4', { unit_of_measurement: '°F' }),
  ] },
  { id: 'kitchen', name: 'Kitchen', intent: 'occupied', set_by: null, hold_until: now + 4700, devices: [
    dev('k1', 'Kitchen lights', 'kitchen', 'light', 'on', { brightness: 255, supported_color_modes: ['brightness'] }),
    dev('k2', 'Under-cabinet strip', 'kitchen', 'light', 'off', { brightness: 0, supported_color_modes: ['brightness'] }),
    dev('k3', 'Coffee maker', 'kitchen', 'switch', 'off', {}),
    dev('k4', 'Kitchen speaker', 'kitchen', 'media', 'off', {}),
    dev('k5', 'Back door', 'kitchen', 'contact', 'off', {}),
    dev('k6', 'Humidity', 'kitchen', 'sensor.humidity', '51', { unit_of_measurement: '%' }),
  ] },
  { id: 'bedroom', name: 'Bedroom', intent: 'asleep', set_by: null, hold_until: null, devices: [
    dev('b1', 'Bedroom lamp', 'bedroom', 'light', 'off', { supported_color_modes: ['brightness'] }),
    dev('b2', 'Bedroom TV', 'bedroom', 'media', 'off', {}),
    dev('b3', 'Ceiling fan', 'bedroom', 'fan', 'on', { percentage: 40 }),
    dev('b4', 'Bedroom blinds', 'bedroom', 'cover', 'closed', { current_position: 0 }),
  ] },
  { id: 'office', name: 'Office', intent: 'occupied', set_by: null, hold_until: null, devices: [
    dev('o1', 'Desk lamp', 'office', 'light', 'on', { brightness: 180, supported_color_modes: ['brightness'] }),
    dev('o2', 'Monitor light', 'office', 'light', 'unavailable', { supported_color_modes: ['brightness'] }),
    dev('o3', 'Office plug', 'office', 'switch', 'on', {}),
  ] },
  { id: 'front', name: 'Front door', intent: 'occupied', set_by: null, hold_until: null, devices: [
    dev('f1', 'Front door', 'front', 'lock', 'locked', {}),
    dev('f2', 'Doorbell', 'front', 'camera', 'streaming', {}),
    dev('f3', 'Porch light', 'front', 'light', 'off', { supported_color_modes: ['onoff'] }),
  ] },
  { id: 'garage', name: 'Garage', intent: 'occupied', set_by: null, hold_until: null, devices: [
    dev('g1', 'Garage View', 'garage', 'camera', 'idle', {}),
    dev('g2', 'Garage door', 'garage', 'cover', 'closed', {}),
  ] },
  { id: 'backyard', name: 'Backyard', intent: 'occupied', set_by: null, hold_until: null, devices: [
    dev('y1', 'Backyard cam', 'backyard', 'camera', 'recording', { light: 'y1l' }),   // a floodlight cam: the viewer offers its lamp
    dev('y1l', 'Backyard cam Light', 'backyard', 'light', 'off', {}),
    dev('y2', 'Robot mower', 'backyard', 'vacuum', 'docked', {}),
  ] },
  { id: 'bath', name: 'Bathroom', intent: 'occupied', set_by: null, hold_until: null, devices: [] },
  { id: 'unassigned', name: 'New devices', intent: 'occupied', set_by: null, hold_until: null, devices: [
    dev('u1', 'Hue color lamp 1', 'unassigned', 'light', 'off', { supported_color_modes: ['hs'] }),
    dev('u2', 'Smart plug', 'unassigned', 'switch', 'off', {}),
  ] },
]
const home = { name: "Temi's house", temp_unit: '°F', rooms }
const status = { driver: process.env.ENGINE === 'down' ? 'down' : 'ready', reason: process.env.ENGINE === 'down' ? "The hub's engine is not answering yet." : '',
  setup_done: process.env.FRESH !== '1', owner: 'Temi', home: "Temi's house", location: true, rooms: 8, devices: 30, locked: process.env.LOCKED === '1',
  drivers: [
    { id: 'mqtt', name: 'Messages', state: 'ready', text: 'Running', port: 1883 },
    { id: 'zigbee', name: 'Zigbee radio', state: 'ready', text: 'Stick on USB', port: 8080 },
    { id: 'zwave', name: 'Z-Wave radio', state: 'off', text: 'No stick found', port: 3000 },
    { id: 'matter', name: 'Matter', state: 'ready', text: 'Running', port: 5580 },
    { id: 'ring', name: 'Ring', state: 'sign-in', text: 'Needs a sign-in', port: 55123 },
  ], problems: [] }
const ambient = { location: { name: 'Holts Summit, MO', lat: 38.6355985, lon: -92.1176322 }, weather: { id: 'w', condition: process.env.WX || 'partlycloudy', temperature: 78, unit: '°F', humidity: 48, wind_speed: 6, wind_unit: 'mph' } }
const scenes = { movie: [['light', 'off', {}], ['media', 'on', {}]], guests: [['light', 'on', {}]], asleep: [['light', 'off', {}], ['media', 'off', {}], ['lock', 'lock', {}]], empty: [['light', 'off', {}], ['media', 'pause', {}]], away: [['light', 'off', {}], ['media', 'off', {}], ['switch', 'off', {}], ['lock', 'lock', {}]] }
const events = [
  { ts: now - 40, kind: 'state', subject: 'mo1', old: 'off', new: 'on', source: 'ha', detail: null },
  { ts: now - 300, kind: 'state', subject: 'm1', old: 'paused', new: 'playing', source: 'ha', detail: JSON.stringify({ media_title: 'The Bear' }) },
  { ts: now - 900, kind: 'intent', subject: 'living', old: 'occupied', new: 'movie', source: 'rule:evening-lights', detail: null },
  { ts: now - 1500, kind: 'state', subject: 'f1', old: 'unlocked', new: 'locked', source: 'ha', detail: null },
  { ts: now - 2400, kind: 'state', subject: 'k5', old: 'on', new: 'off', source: 'ha', detail: null },
  { ts: now - 5400, kind: 'state', subject: 'o2', old: 'on', new: 'unavailable', source: 'ha', detail: null },
]
const rules = { rules: [
  { id: 'evening-lights', name: 'Living room lights on at dusk', room: 'living', when: { sun: 'set', offset: -1200 }, then: { intent: 'movie' }, enabled: true },
  { id: 'kitchen-motion', name: 'Kitchen lights when someone walks in', room: 'kitchen', when: { motion: true }, if: [['sun', 'below', 'horizon']], then: { intent: 'occupied' }, enabled: true },
  { id: 'bed-off', name: 'Bedroom off after 20 minutes of nothing', room: 'bedroom', when: { idle: 1200 }, then: { intent: 'empty' }, enabled: false },
  { id: 'backyard-evening', name: 'Backyard light on when someone is out there after dark', room: 'backyard', when: { motion: true }, then: { light: 'on' }, enabled: true },
], drafts: [], valid: true, errors: [] }
const why = [
  { ts: now - 900, kind: 'intent', subject: 'living', old: 'occupied', new: 'movie', source: 'rule:evening-lights', detail: JSON.stringify({ rule: 'evening-lights', when: { sun: 'set', offset: -1200 }, if: [] }) },
  { ts: now - 7200, kind: 'intent', subject: 'living', old: 'empty', new: 'occupied', source: 'panel', detail: null },
]
const discovered = process.env.FOUND === '0' ? [] : [{ flow_id: 'f1', handler: 'sonos', kind: 'speaker', title: 'Sonos Roam', source: 'zeroconf' }, { flow_id: 'f2', handler: 'cast', kind: 'tv', title: 'Chromecast (Den)', source: 'zeroconf' }]
const catalog = [{ domain: 'hue', name: 'Philips Hue', brand: 'Philips', local: true }, { domain: 'nest', name: 'Google Nest', brand: 'Google', local: false }, { domain: 'ring', name: 'Ring', local: false }, { domain: 'tplink', name: 'TP-Link Kasa', local: true }]

// A picture for cameras and album art: a soft gradient, so tiles look occupied.
const pic = (a, b) => `<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='${a}'/><stop offset='1' stop-color='${b}'/></linearGradient></defs><rect width='640' height='360' fill='url(#g)'/><ellipse cx='420' cy='300' rx='300' ry='90' fill='rgba(0,0,0,.25)'/></svg>`
const PICS = { f2: pic('#3b4a5c', '#1b2230'), g1: pic('#2f2a26', '#14110f'), y1: pic('#2c4a2f', '#111a12'), m1: pic('#7a3b2a', '#2a1410') }

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json' }
const json = (res, body) => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)) }

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x')
  const p = url.pathname
  if (p === '/setup/status') return json(res, status)
  if (p === '/home') return json(res, home)
  if (p === '/ambient') return json(res, ambient)
  if (p === '/scenes') return json(res, scenes)
  if (p === '/events') return json(res, events)
  if (p === '/rules') return json(res, rules)
  if (p === '/discovered') return json(res, discovered)
  if (p === '/catalog') return json(res, catalog)
  if (p === '/pair') return json(res, { state: 'idle' })
  if (p === '/assistant') return json(res, { available: true, configured: false, source: null, model: 'claude-sonnet-5' })
  if (p === '/setup/drivers') return json(res, status)
  if (p === '/setup/advanced') return json(res, { url: 'http://hub.local:8123/', username: 'hub', password: 'secret' })
  if (/^\/rooms\/[^/]+\/why/.test(p)) return json(res, why)
  if (/^\/devices\/[^/]+\/stream/.test(p)) { res.writeHead(502); return res.end() }   // no video here: the viewer settles for stills
  const img = p.match(/^\/devices\/([^/]+)\/image/)
  if (img) { res.writeHead(200, { 'Content-Type': 'image/svg+xml' }); return res.end(PICS[img[1]] ?? pic('#333', '#111')) }
  if (req.method === 'POST') return json(res, { ok: true })
  let f = path.join(DIST, p === '/' ? 'index.html' : p)
  if (!fs.existsSync(f)) f = path.join(DIST, 'index.html')
  if (!fs.existsSync(f)) { res.writeHead(503, { 'Content-Type': 'text/plain' }); return res.end('No dist/ yet: run `npm run build` first, or use `BRAIN=http://localhost:' + PORT + ' npm run dev`.') }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' })
  fs.createReadStream(f).pipe(res)
})
// keep the websocket open so the panel shows Connected; nothing is ever sent
server.on('upgrade', (req, socket) => {
  if (/\/webrtc$/.test(req.url)) return socket.destroy()   // no WebRTC here either
  const key = req.headers['sec-websocket-key']
  const accept = crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64')
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n')
  socket.on('error', () => {})
})
server.listen(PORT, () => console.log(`mock brain on http://localhost:${PORT}/`))
