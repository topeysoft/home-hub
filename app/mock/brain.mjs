/* A stand-in for the brain, for looking at the panel without a hub: serves ../dist and enough JSON for a lived-in
   house of eight rooms. `npm run mock`, then open http://localhost:8399/ (every ?at= ?wx= ?month= ?room= ?sheet= ?setup=
   preview works), or `BRAIN=http://localhost:8399 npm run dev` for hot reload against it.
   Knobs: PORT, WX=rainy (a condition), FOUND=0 (nothing new nearby), ENGINE=down (the engine-starting screen),
   LOCKED=1 (a code is set), FRESH=1 (first run), ASK=1 (a phone is asking to join; needs LOCKED=1), ?join=1 (the join screen). Nothing here talks to a real device; every POST or DELETE says ok. */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const PORT = Number(process.env.PORT || 8399)
const now = Math.floor(Date.now() / 1000)

const dev = (id, name, room_id, capability, state, attrs = {}, maker = null) => ({ id, name, room_id, capability, state, attrs, maker })   // maker: what the registry knows, often nothing
const rooms = [
  { id: 'living', name: 'Living room', intent: 'movie', set_by: 'rule:evening-lights', hold_until: null, devices: [
    dev('l1', 'Ceiling light', 'living', 'light', 'on', { brightness: 90, color_temp_kelvin: 2700, supported_color_modes: ['brightness', 'color_temp'] }, 'Philips Hue'),
    dev('l2', 'Floor lamp', 'living', 'light', 'on', { brightness: 60, supported_color_modes: ['brightness'] }),
    dev('l3', 'Reading lamp', 'living', 'light', 'off', { supported_color_modes: ['onoff'] }),
    dev('m1', 'Living room TV', 'living', 'media', 'playing', { media_title: 'The Bear', media_artist: 'Season 3, Episode 4', app_name: 'Disney+', volume_level: 0.35, entity_picture: '/x.jpg', media_position: 1421, media_duration: 3740 }),
    dev('s1', 'Sonos', 'living', 'media', 'paused', { media_title: 'Blue in Green', media_artist: 'Miles Davis', volume_level: 0.2 }),
    dev('c1', 'Blinds', 'living', 'cover', 'open', { current_position: 70 }, 'IKEA'),
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
/* SWITCHES=11 fills New devices with a bridge's worth of look-alike wall switches -- the moment
   naming by touch exists for, and the one that cannot be judged with two rows in the list. Their
   names are the ones the bridge actually gives them, addresses and all, because that is the problem. */
const MESH = ['0004', '0005', '0006', '0008', '000a', '000b', '000e', '0010', '0011', '0014', '0016']
const unassigned = rooms.find(r => r.id === 'unassigned')
for (let i = 0; i < Number(process.env.SWITCHES || 0) && i < MESH.length; i++)
  unassigned.devices.push(dev(`mesh${MESH[i]}`, `Brilliant switch ${MESH[i]}`, 'unassigned', 'light', 'off', { brightness: 0, has_motion: true }))

/* A press, which is the whole mechanism: a switch announcing itself because a human touched it.
   POST /press or /press/<id> makes one happen; PRESS=1 rotates through them on its own so the
   screen can just be watched. Mock only -- on a hub this is the driver's own state event. */
let pressedId = null, pressedAt = 0
function pressEvent() {
  if (process.env.PRESS === '1' && !pressedId) { pressedId = unassigned.devices[0]?.id; pressedAt = Date.now() / 1000 }
  if (!pressedId || Date.now() / 1000 - pressedAt > 45) return []
  return [{ ts: pressedAt, kind: 'state', subject: pressedId, old: 'off', new: 'on', source: 'device', detail: null }]
}

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
/* What changed, in a house's words (docs/updates.md piece 4). Off unless asked for, so the panel's
   ordinary previews and the e2e run see the hub page exactly as they did before: WHATSNEW=1 puts the
   morning-after card on Home and the What's new row under This hub. */
const releaseNotes = [
  { version: '0.3.0', what: ['Speakers remember how loud you had them.', 'The kitchen comes up on the wall faster after the hub restarts.'], details: 'Longer, for whoever goes looking.' },
  { version: '0.2.2', what: ['Blinds stop where you let go of them.'], details: '' },
]
if (process.env.WHATSNEW === '1') {
  status.version = 'v0.3.0'
  status.update = { version: 'v0.3.0', commit: 'abc123def456', channel: 'release', latest: null, whats_new: releaseNotes[0],
                    available: false, offer: false, rejected: null, auto: true, verified: true,
                    checked: Date.now() / 1000, requested: false, state: null, error: null }
}
// who the house knows and who is in, for the household strip; PEOPLE=0 is a house with nobody set up
const presence = process.env.PEOPLE === '0'
  ? { somebody: null, since: null, source: null, people: [], alarm: null }
  : { somebody: true, since: Date.now() - 3600e3, source: 'people', people: [{ name: 'Temi', home: true }, { name: 'Sam', home: false }, { name: 'Ade', home: true }], alarm: null }
/* What is coming, the way a real hub shapes it (brain/hub/forecast.py). Built from the hour the
   panel is actually running in, so ?at= previews land in the middle of it rather than behind it:
   the afternoon warms, it rains from four until six, and it clears. FORECAST=0 takes it away, which
   is the house this panel still has to work on -- plenty of weather integrations serve none. */
const forecastHours = () => {
  /* A real hub carries twelve hours from now (brain/hub/forecast.py). This carries thirty-six from
     MIDNIGHT instead, which is the one difference worth having: ?at= previews an hour of the day on
     the panel and the mock cannot see that query, so a forecast that started at the real clock would
     leave a preview of the evening with two rows and a preview of the morning with none. Starting at
     midnight means every hour anybody previews has a full row of hours after it. */
  const midnight = new Date(); midnight.setHours(0, 0, 0, 0)
  const hour = h => {
    const t = Math.round(69 + 11 * Math.sin(((h % 24) - 9) / 24 * Math.PI * 2))   // coldest around three, warmest around three
    const wet = (h % 24) >= 16 && (h % 24) < 18                                    // it rains from four until six
    const night = (h % 24) < 6 || (h % 24) >= 20
    return { at: new Date(midnight.getTime() + h * 3600e3).toISOString(),
             condition: wet ? 'rainy' : night ? 'clear-night' : (h % 24) % 5 === 0 ? 'cloudy' : 'partlycloudy',
             temperature: t, rain: wet ? 80 : 10 }
  }
  /* and the curve is anchored to the house's own reading, so the row for the hour it is now says
     what the big number on the pane says. A mock whose forecast disagrees with its own weather by
     twenty degrees is a mock that makes every screenshot look like a bug. */
  const rows = Array.from({ length: 36 }, (_, h) => hour(h))
  const nowRow = rows[new Date().getHours()]
  const shift = 78 - nowRow.temperature
  return rows.map(r => ({ ...r, temperature: r.temperature + shift }))
}
const forecastDays = () => {
  const midnight = new Date(); midnight.setHours(0, 0, 0, 0)
  const shape = [[0, 84, 61, 'rainy'], [1, 88, 64, 'sunny'], [2, 77, 59, 'partlycloudy'], [3, 79, 60, 'cloudy'], [4, 81, 62, 'sunny']]
  return shape.map(([d, hi, lo, c]) => ({ at: new Date(midnight.getTime() + d * 86400e3).toISOString(), condition: c, high: hi, low: lo, rain: c === 'rainy' ? 70 : 10 }))
}
const ambient = { location: { name: 'Holts Summit, MO', lat: 38.6355985, lon: -92.1176322 }, weather: { id: 'w', condition: process.env.WX || 'partlycloudy', temperature: 78, unit: '°F', humidity: 48, wind_speed: 6, wind_unit: 'mph' },
  forecast: process.env.FORECAST === '0' ? null : { hourly: forecastHours(), daily: forecastDays() },
  look: { feel: process.env.FEEL || 'calm', tone: process.env.TONE || 'follow', face: process.env.FACE || 'paper', layout: process.env.LAYOUT || 'auto', nav: process.env.NAV || 'auto' } }   // FEEL=nightfall LAYOUT=rail TONE=pastel NAV=top FACE=glass start the house somewhere else
const scenes = { movie: [['light', 'off', {}], ['media', 'on', {}]], guests: [['light', 'on', {}]], asleep: [['light', 'off', {}], ['media', 'off', {}], ['lock', 'lock', {}]], empty: [['light', 'off', {}], ['media', 'pause', {}]], away: [['light', 'off', {}], ['media', 'off', {}], ['switch', 'off', {}], ['lock', 'lock', {}]] }
const events = [
  { ts: now - 40, kind: 'state', subject: 'mo1', old: 'off', new: 'on', source: 'ha', detail: null },
  { ts: now - 300, kind: 'state', subject: 'm1', old: 'paused', new: 'playing', source: 'ha', detail: JSON.stringify({ media_title: 'The Bear' }) },
  { ts: now - 900, kind: 'intent', subject: 'living', old: 'occupied', new: 'movie', source: 'rule:evening-lights', detail: null },
  { ts: now - 1500, kind: 'state', subject: 'f1', old: 'unlocked', new: 'locked', source: 'ha', detail: null },
  { ts: now - 2400, kind: 'state', subject: 'k5', old: 'on', new: 'off', source: 'ha', detail: null },
  { ts: now - 5400, kind: 'state', subject: 'o2', old: 'on', new: 'unavailable', source: 'ha', detail: null },
]
/* A day per device, so an opened pane has a foot and a sensor has a shape. The hub answers
   /events?subject=<id> from the same log; this is that answer, made up for one house.
   `hrs` is hours ago, and a row is [hours, kind, old, new, source, detail]. */
const day = (id, rows) => rows.map(([hrs, kind, old, nw, source = 'ha', detail = null]) =>
  ({ ts: now - Math.round(hrs * 3600), kind, subject: id, old, new: nw, source, detail: detail && JSON.stringify(detail) }))
/* a thermometer's day: a reading each time it moved, which is what the pane draws a line through */
const temps = [[13, 64.2], [11.5, 65.8], [10, 68.1], [8.5, 71.4], [7, 74.9], [5.5, 77.2], [4.5, 78.0], [3, 76.6], [2, 75.1], [1, 74.2], [0.3, 73.4]]
const perDevice = [
  ...day('l1', [[1.6, 'action', null, 'on', 'user', { brightness_pct: 35 }], [2.5, 'state', 'off', 'on'],
                [6.2, 'state', 'on', 'off'], [12, 'state', 'off', 'on']]),
  ...day('l2', [[2.4, 'state', 'off', 'on'], [9, 'state', 'on', 'off']]),
  ...day('m1', [[0.6, 'action', null, 'play', 'user'], [5.6, 'state', 'playing', 'off']]),
  ...day('t1', [[1.1, 'action', null, 'set', 'user', { temperature: 71 }], [1.05, 'state', 'off', 'cool'],
                [6.5, 'state', 'cool', 'off'], [12.7, 'action', null, 'set', 'user', { temperature: 70 }]]),
  ...day('c1', [[12.5, 'action', null, 'set', 'user', { position: 70 }], [12.55, 'state', 'closed', 'open'], [21.3, 'state', 'open', 'closed']]),
  ...day('f1', [[1.9, 'state', 'locked', 'unlocked'], [2.4, 'action', null, 'unlock', 'user'], [6.6, 'state', 'unlocked', 'locked'], [11.3, 'state', 'locked', 'unlocked']]),
  ...day('y1', [[0.03, 'state', 'streaming', 'recording'], [1.6, 'state', 'idle', 'recording'], [2.9, 'state', 'recording', 'idle'], [8.3, 'state', 'idle', 'recording']]),
  ...day('y2', [[5.2, 'state', 'cleaning', 'docked'], [7.4, 'action', null, 'start', 'user'], [7.35, 'state', 'docked', 'cleaning']]),
  ...day('b3', [[22, 'action', null, 'set', 'user', { percentage: 40 }], [22.1, 'state', 'off', 'on']]),
  ...day('k3', [[12.4, 'state', 'on', 'off'], [12.9, 'action', null, 'on for 30 min', 'user', { minutes: 30 }]]),
  /* motion through the day, which is the strip a sensor's pane is read for */
  ...day('mo1', [[0.4, 'state', 'on', 'off'], [0.45, 'state', 'off', 'on'], [1.2, 'state', 'on', 'off'],
                 [1.25, 'state', 'off', 'on'], [3.1, 'state', 'on', 'off'], [3.2, 'state', 'off', 'on'], [6.8, 'state', 'on', 'off'],
                 [6.9, 'state', 'off', 'on'], [11.4, 'state', 'on', 'off'], [11.5, 'state', 'off', 'on']]),
  ...day('k5', [[3.6, 'state', 'on', 'off'], [3.7, 'state', 'off', 'on'], [7.2, 'state', 'on', 'off'], [7.3, 'state', 'off', 'on'],
                [11.1, 'state', 'on', 'off'], [11.2, 'state', 'off', 'on']]),
  ...day('te1', temps.map(([h, v], i) => [h, 'state', i ? String(temps[i - 1][1]) : null, String(v)])),
  ...day('k6', [[0.5, 'state', '49', '51'], [4, 'state', '54', '49'], [8, 'state', '47', '54']]),
]
const rules = { rules: [
  { id: 'evening-lights', name: 'Living room lights on at dusk', room: 'living', when: { sun: 'set', offset: -1200 }, then: { intent: 'movie' }, enabled: true },
  { id: 'kitchen-motion', name: 'Kitchen lights when someone walks in', room: 'kitchen', when: { motion: true }, if: [['sun', 'below', 0]], then: { intent: 'occupied' }, enabled: true },
  { id: 'bed-off', name: 'Bedroom off after 20 minutes of nothing', room: 'bedroom', when: { idle: 1200 }, then: { intent: 'empty' }, enabled: false },
  { id: 'backyard-evening', name: 'Backyard light on when someone is out there after dark', room: 'backyard', when: { motion: true }, then: { light: 'on' }, enabled: true },
], drafts: [], valid: true, errors: [] }
const why = [
  { ts: now - 900, kind: 'intent', subject: 'living', old: 'occupied', new: 'movie', source: 'rule:evening-lights', detail: JSON.stringify({ rule: 'evening-lights', when: { sun: 'set', offset: -1200 }, if: [] }) },
  { ts: now - 7200, kind: 'intent', subject: 'living', old: 'empty', new: 'occupied', source: 'panel', detail: null },
]
const discovered = process.env.FOUND === '0' ? [] : [{ flow_id: 'f1', handler: 'sonos', kind: 'speaker', title: 'Sonos Roam', source: 'zeroconf' }, { flow_id: 'f2', handler: 'cast', kind: 'tv', title: 'Chromecast (Den)', source: 'zeroconf' }]
// NEEDSLOOK=1 gives Home its quiet list. Every line is a job: it says what can be done about it in `acts`,
// and a fault gathers what went quiet behind it in `with` -- one dead radio is one line and not seven.
// The shape here is the shape a real house was showing: a radio down, and everything on it gone with it.
const quietOnes = [
  { id: 'l4', name: 'Front door', where: 'Hall · a lock' },
  { id: 'l5', name: 'Dimmer', where: 'Living room · a light' },
  { id: 'l6', name: 'Home Theater Light', where: 'Den · a light' },
  { id: 'l7', name: 'Holts Summit Alarm Siren', where: 'Hall · a plug' },
  { id: 'l8', name: 'Porch light', where: 'Porch · a light' },
  { id: 'l9', name: 'Garage sensor', where: 'Garage · a plug' },
]
const notes = process.env.NEEDSLOOK ? [
  { kind: 'driver', subject: 'nest', since: null, text: 'Google Nest needs signing in again: home-hub.', with: [],
    acts: [{ do: 'Sign in again', act: 'flow', to: 'r1' }] },
  { kind: 'driver', subject: 'zwave', since: null, text: 'Z-Wave radio is not running: could not connect.', with: quietOnes,
    acts: [{ do: 'Try again', act: 'part', to: 'zwave' }] },
  { kind: 'driver', subject: 'e-hue', since: null, text: 'Hue bridge could not connect: no route to host', with: [],
    acts: [{ do: 'Try again', act: 'entry', to: 'e-hue' }] },
  { kind: 'offline', subject: 'l1', name: 'Bedroom TV', where: 'Bedroom · a speaker', since: now - 86400 * 9,
    text: 'Bedroom TV has been offline since Sep 6.',
    acts: [{ do: 'Check again', act: 'check', to: 'l1' },
           { do: "It's gone, remove it", act: 'forget', to: 'l1', yes: 'Yes, remove Bedroom TV',
             ask: 'Remove Bedroom TV from the house? It comes off the account that brought it.' }] },
  { kind: 'storage', subject: null, since: null, acts: [], text: "The hub's storage is nearly full: 35.5 GB left." },
] : []
// NEEDSLOOK=many: a house where a lot has gone quiet with nothing in common, for the fold on the page.
if (process.env.NEEDSLOOK === 'many') {
  for (const q of quietOnes.concat(quietOnes.map(q => ({ ...q, id: q.id + 'b', name: q.name + ' 2' })))) {
    notes.splice(-1, 0, { kind: 'offline', subject: q.id, name: q.name, where: q.where, since: now - 86400,
      text: `${q.name} has been offline since yesterday.`,
      acts: [{ do: 'Check again', act: 'check', to: q.id },
             { do: "It's gone, remove it", act: 'forget', to: q.id, yes: `Yes, remove ${q.name}`,
               ask: `Remove ${q.name} from the house? It comes off the account that brought it.` }] })
  }
}
// the sign-in conversation behind that first line: HA asks for the password again, nothing else
const signIn = { type: 'form', flow_id: 'r1', handler: 'nest', kind: 'Google Nest', step_id: 'reauth_confirm',
  hint: 'Google signed this hub out. Signing in again brings the cameras, doorbell and thermostat back.',
  fields: [{ name: 'password', label: 'Password', kind: 'password', required: true }] }
const catalog = [{ domain: 'hue', name: 'Philips Hue', brand: 'Philips', local: true }, { domain: 'nest', name: 'Google Nest', brand: 'Google', local: false }, { domain: 'ring', name: 'Ring', local: false }, { domain: 'tplink', name: 'TP-Link Kasa', local: true }]

// A picture for cameras and album art: a soft gradient, so tiles look occupied.
const pic = (a, b) => `<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='${a}'/><stop offset='1' stop-color='${b}'/></linearGradient></defs><rect width='640' height='360' fill='url(#g)'/><ellipse cx='420' cy='300' rx='300' ry='90' fill='rgba(0,0,0,.25)'/></svg>`
const PICS = { f2: pic('#3b4a5c', '#1b2230'), g1: pic('#2f2a26', '#14110f'), y1: pic('#2c4a2f', '#111a12'), m1: pic('#7a3b2a', '#2a1410') }

const started = Date.now()      // the mock's frames are as old as the mock, bar the one that is deliberately stale

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json' }
const json = (res, body) => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)) }

const phones = { phones: [
  { id: 'w', name: 'This wall', kind: 'wall', joined: now - 86400 * 30, expires: null, remote: false, last_seen: now, how: 'setup', me: true },
  { id: 'p1', name: "Temi's iPhone", kind: 'phone', joined: now - 86400 * 20, expires: null, remote: false, last_seen: now - 3600, how: 'code', me: false },
  { id: 'p2', name: "Nadine's Android phone", kind: 'phone', joined: now - 3600, expires: now + 86400 * 2, remote: false, last_seen: now - 600, how: 'wall', me: false },
], asks: process.env.ASK ? [{ id: 'a1', name: "Sam's iPhone", kind: 'phone', asked: now - 30 }] : [] }

/* ---------- a bridge being set up ----------
   The real brain watches a thing on a cable; this walks a clock, so the sheet can be seen moving.
   BRIDGE=cable starts at the knock and runs the whole way; the other values pin one moment. */
const BRIDGE = process.env.BRIDGE || ''
/* BRIDGES=1 is a house that already HAS a bridge and is not busy -- which is the normal case, and the
   one that puts the Wall switch door on the Add screen. WAITING=1 is a new switch sitting there
   unprovisioned, which is what that door then has something to say about. */
const HAVE = { bridges: Number(process.env.BRIDGES || (process.env.BRIDGE ? 1 : 0)), waiting: Number(process.env.WAITING || 0) }
let bridgeAt = 0                      // when "yes, that's mine" was pressed; 0 = still knocking
let bridgePinned = null               // set by dismiss/placed, or by a pinned BRIDGE value
function bridgeNow() { return { ...HAVE, ...job() } }
function job() {
  if (!BRIDGE) return { state: 'none' }
  if (bridgePinned) return bridgePinned === 'ready'
    ? { state: 'ready', how: 'cable', switches: 11, unplaced: 8 }
    : { state: 'none' }
  if (BRIDGE !== 'cable') {
    return {
      knocking: { state: 'knocking', how: 'air' },
      working: { state: 'working', how: 'cable', step: 'keys' },
      placing: { state: 'placing', how: 'cable', switches: 11, signal: 'strong' },
      ready: { state: 'ready', how: 'cable', switches: 11, unplaced: 8 },
      failed: { state: 'failed', how: 'cable', text: 'The bridge stopped answering halfway through. Unplug it, plug it back into the hub, and it will pick up where it left off.' },
    }[BRIDGE] ?? { state: 'none' }
  }
  if (!bridgeAt) return { state: 'knocking', how: 'cable' }
  const t = (Date.now() - bridgeAt) / 1000
  if (t < 4) return { state: 'working', how: 'cable', step: 'software' }
  if (t < 8) return { state: 'working', how: 'cable', step: 'wifi' }
  if (t < 12) return { state: 'working', how: 'cable', step: 'keys' }
  /* the walk: nothing heard at first, then a switch or two, then the lot */
  const heard = t < 16 ? 0 : t < 20 ? 2 : 11
  if (t < 24) return { state: 'placing', how: 'cable', switches: heard, signal: heard ? (heard > 4 ? 'strong' : 'weak') : 'none' }
  return { state: 'ready', how: 'cable', switches: 11, unplaced: 8 }
}

const BRAIN = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'brain')
/* the last resort when there is no brain venv to draw with: a code-shaped picture that decodes to
   nothing. It is honest about being a picture only in this name. */
const FAKE_QR = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 29 29'><rect width='29' height='29' fill='#fff'/><path d='M2 2h7v7H2zM3 3v5h5V3zM4 4h3v3H4zM20 2h7v7h-7zM21 3v5h5V3zM22 4h3v3h-3zM2 20h7v7H2zM3 21v5h5v-5zM4 22h3v3H4zM11 2h2v2h-2zM14 3h2v2h-2zM11 6h3v2h-3zM16 7h2v2h-2zM2 11h2v2H2zM5 12h2v2H5zM8 11h2v3H8zM11 10h2v3h-2zM14 11h3v2h-3zM18 10h2v3h-2zM21 11h2v2h-2zM24 12h3v2h-3zM3 15h3v2H3zM7 16h2v2H7zM11 14h2v3h-2zM14 15h2v3h-2zM17 14h3v2h-3zM21 15h2v3h-2zM24 16h3v2h-3zM11 19h2v2h-2zM14 20h3v2h-3zM18 19h2v3h-2zM21 20h2v2h-2zM24 19h3v3h-3zM11 23h3v2h-3zM15 24h2v3h-2zM18 23h3v2h-3zM22 24h2v2h-2zM25 23h2v4h-2z'/></svg>`

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x')
  const p = url.pathname
  if (p === '/setup/status') return json(res, status)
  if (p === '/update/notes') return json(res, { notes: releaseNotes[0], history: releaseNotes })
  if (p === '/update/check' && req.method === 'POST') { if (status.update) status.update.checked = Date.now() / 1000; return json(res, status.update ?? {}) }
  if (p === '/update/notes/seen' && req.method === 'POST') { if (status.update) status.update.whats_new = null; return json(res, status.update ?? {}) }
  if (p === '/home') return json(res, home)
  if (p === '/ambient') return json(res, ambient)
  if (p === '/presence') return json(res, presence)
  if (p === '/scenes') return json(res, scenes)
  /* the hub narrows its log by subject; a pane's foot is that query and nothing else */
  if (p.startsWith('/press') && req.method === 'POST') {
    pressedId = p.split('/')[2] || unassigned.devices[Math.floor(Math.random() * unassigned.devices.length)]?.id
    pressedAt = Date.now() / 1000
    const d = unassigned.devices.find(x => x.id === pressedId)
    if (d) { d.state = d.state === 'on' ? 'off' : 'on'; if (d.attrs) d.attrs.brightness = d.state === 'on' ? 180 : 0; push({ type: 'device', device: d }) }
    return json(res, { ok: true, id: pressedId, state: d?.state })
  }
  if (p === '/events') {
    const subject = url.searchParams.get('subject')
    const limit = Number(url.searchParams.get('limit')) || 100
    const all = [...pressEvent(), ...events, ...perDevice].sort((a, b) => b.ts - a.ts)
    return json(res, (subject ? all.filter(e => e.subject === subject) : all).slice(0, limit))
  }
  if (p === '/rules') return json(res, rules)
  if (p === '/discovered') return json(res, discovered)
  if (p === '/health') return json(res, { notes })
  // What a speaker can play. The real brain generates the noises and lists the sounds folder; here it is
  // a fixed shelf, so the sounds sheet has something to draw without a hub or a speaker in the room.
  if (p === '/sounds') return json(res, {
    sounds: [
      { id: 'white', name: 'White noise', kind: 'made', ready: true },
      { id: 'pink', name: 'Pink noise', kind: 'made', ready: true },
      { id: 'brown', name: 'Brown noise', kind: 'made', ready: true },
      { id: 'rain', name: 'Rain', kind: 'file', ready: true },
      { id: 'waves', name: 'Waves', kind: 'file', ready: false },
    ],
    playing: {},
    folder: '/data/sounds',
  })
  // the two ways out of a quiet thing, and the way back into a part that stopped
  if (p.startsWith('/devices/') && p.endsWith('/check') && req.method === 'POST') {
    const id = p.split('/')[2]
    const n = notes.find(x => x.subject === id)
    return json(res, { ok: true, answering: false, text: `${n?.name || 'It'} still is not answering.` })
  }
  if (p === '/drivers/zwave/retry' && req.method === 'POST') return json(res, { ok: true, drivers: status.drivers })
  if (p === '/flows/r1') {
    if (req.method !== 'POST') return json(res, signIn)
    const i = notes.findIndex(n => n.acts?.some(a => a.to === 'r1')); if (i >= 0) notes.splice(i, 1)   // answered: the line on Home goes
    return json(res, { type: 'create_entry', flow_id: 'r1', handler: 'nest', kind: 'Google Nest', entry_title: 'home-hub' })
  }
  if (p === '/catalog') return json(res, catalog)
  /* A bridge being set up. BRIDGE=cable walks the whole job the way a real one does -- software,
     Wi-Fi, keys, then the walk to find it a socket -- so the sheet can be watched rather than
     described. BRIDGE=knocking|working|placing|ready|failed pins one moment instead. */
  if (p === '/bridge') return json(res, bridgeNow())
  /* Letting a new switch in: the phone sends whatever its camera read, whole. */
  if (p === '/bridge/switches' && req.method === 'POST') {
    HAVE.waiting = Math.max(0, HAVE.waiting - 1)
    const d = dev('mesh-new', 'Brilliant switch 0019', 'unassigned', 'light', 'off', { brightness: 0, has_motion: true })
    unassigned.devices.push(d)
    push({ type: 'device', device: d })
    return json(res, { state: 'done', device_id: d.id, name: d.name, text: 'A light that dims, and a motion sensor.' })
  }
  if (p.startsWith('/bridge/') && req.method === 'POST') {
    const what = p.split('/')[2]
    if (what === 'adopt') { bridgeAt = Date.now(); bridgePinned = null }       // yes, that one is mine: the job starts
    if (what === 'dismiss') { bridgePinned = 'none'; }
    if (what === 'placed') { bridgePinned = 'ready' }
    return json(res, bridgeNow())
  }
  if (p === '/pair') return json(res, { state: 'idle' })
  if (p === '/assistant') return json(res, { available: true, configured: false, source: null, model: 'claude-sonnet-5' })
  if (p === '/setup/drivers') return json(res, status)
  if (p === '/setup/advanced') return json(res, { url: 'http://hub.local:8123/', username: 'hub', password: 'secret' })
  if (/^\/rooms\/[^/]+\/why/.test(p)) return json(res, why)
  if (p === '/suggestions') return json(res, { items: [
    { id: 'u1', name: 'Colour lamp', room: 'living', why: 'the same unit as the floor lamp', source: 'assistant' },
    { id: 'u2', name: 'Plug', room: '', why: 'a plainer name', source: 'house' }], assistant: true })
  if (p === '/phone') return json(res, { ip: '192.168.1.40' })
  if (p === '/phones/me') return json(res, { locked: !!process.env.LOCKED, paired: true, home: 'Main Palace', phone: null })
  if (p === '/phones') return json(res, phones)
  /* the accounts page: one of each state, so the page can be read without a house behind it.
     ACCOUNTS=0 empties it (the nothing-signed-in-yet case). */
  if (p === '/accounts') return json(res, { accounts: process.env.ACCOUNTS === '0' ? [] : [
    { id: 'e-nest', kind: 'Google Nest', name: 'Google Nest', state: 'signin', why: '', flow: 'flow-nest', things: 4 },
    { id: 'e-ring', kind: 'Ring', name: 'Ring', state: 'stopped', why: 'the key it was given has been revoked', flow: null, things: 3 },
    { id: 'e-hue', kind: 'Philips Hue', name: 'Philips Hue bridge', state: 'on', why: '', flow: null, things: 11 },
    { id: 'e-tesla', kind: 'Tesla', name: 'Tesla', state: 'on', why: '', flow: null, things: 1 },
  ] })
  if (p === '/phones/ask' && req.method === 'POST') return json(res, { id: 'ask1', name: "Sam's iPhone", kind: 'phone', asked: now })
  if (p.startsWith('/phones/claim/')) return json(res, { state: 'waiting' })
  /* A real code where one can be drawn, and a picture of one where it cannot.

     This used to be a fixed decorative pattern that ignored `text`, which is fine for a screenshot
     and a trap for anything else: the wall's hand-off code and the phone-onboarding code both looked
     right and decoded to nothing, so a camera pointed at the mock silently did nothing at all. The
     hub draws these with qrcode in Python (qr_svg_bytes, brain/hub/api.py); if that venv is here,
     use it, so what the mock shows is the same code the hub would show. */
  if (p === '/qr.svg') {
    const text = url.searchParams.get('text') || ''
    let svg = null
    try {
      svg = execFileSync(path.join(BRAIN, '.venv/bin/python'),
        ['-c', 'import sys; sys.path.insert(0, sys.argv[1]); from hub.api import qr_svg_bytes; sys.stdout.buffer.write(qr_svg_bytes(sys.argv[2]))', BRAIN, text],
        { timeout: 4000 })
    } catch {}
    res.writeHead(200, { 'Content-Type': 'image/svg+xml' })
    return res.end(svg ?? FAKE_QR)
  }
  if (p === '/say' && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => { let t = ''; try { t = JSON.parse(b).text || '' } catch {}
    if (/^(is|are|what|who|how)\b/i.test(t)) return json(res, { kind: 'answer', text: 'Front door is locked.', said: t })
    if (/cosy|cozy|nice/i.test(t)) return json(res, { kind: 'action', device: 'l2', device_name: 'Floor lamp', action: 'on', data: { brightness_pct: 30 }, name: 'Floor lamp on, low', said: t })
    if (/when|every|whenever/i.test(t)) return json(res, { kind: 'rule', id: 'x', name: t, room: 'living', when: { time: '21:00' }, then: { intent: 'movie' }, said: t })
    if (t.length < 4) { res.writeHead(422, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ detail: 'The house didn\'t catch that. Try "kitchen lights off", "movie in the den" or "is the front door locked?". Connect the assistant under Routines to ask in your own words.' })) }
    return json(res, { kind: 'done', text: 'Kitchen lights off.', said: t, count: 2 }) }) }
  if (/^\/devices\/[^/]+\/stream/.test(p)) { res.writeHead(502); return res.end() }   // no video here: the viewer settles for stills
  const img = p.match(/^\/devices\/([^/]+)\/image/)
  if (img) {
    // Dated the way the brain dates a frame: the same picture keeps the time it first appeared, so the
    // panel can be watched telling the truth about a camera that never sends a new one. g1 is that
    // camera -- the still it answers with is an hour old and stays an hour old.
    const body = PICS[img[1]] ?? pic('#333', '#111')
    const tag = `"${Buffer.from(body).length.toString(16)}${img[1]}"`
    const age = img[1] === 'g1' ? 3600 : Math.round((Date.now() - started) / 1000)
    const headers = { 'Cache-Control': 'no-store', ETag: tag, 'X-Frame-Age': String(age) }
    if ((req.headers['if-none-match'] || '').includes(tag)) { res.writeHead(304, headers); return res.end() }
    res.writeHead(200, { 'Content-Type': 'image/svg+xml', ...headers }); return res.end(body)
  }
  if (p === '/look' && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => {
    let v = {}; try { v = JSON.parse(b) } catch {}
    for (const k of ['feel', 'tone', 'layout', 'nav', 'face']) if (v[k]) ambient.look[k] = v[k]   // unknown keys dropped, as the brain does
    json(res, ambient.look)
  }) }
  /* Show this as: the same rule the brain computes, so the pane can be read without a house behind it.
     Kinds that share their controls may stand in for each other and no others -- a plug may be a lamp,
     and may not be a blind. docs/kinds.md. */
  const kindOf = d => (d.kind || d.capability).split('.')[0]
  const CONTROLS = { light: 'onoff', switch: 'onoff', fan: 'onoff', alarm: 'onoff', media: 'onoff+playing', climate: 'temperature', vacuum: 'errand', camera: 'picture' }
  const WORD = { light: 'Light', switch: 'Plug', fan: 'Fan', alarm: 'Alarm', media: 'Speaker', climate: 'Thermostat', vacuum: 'Vacuum', camera: 'Camera' }
  const offerFor = d => {
    const wants = CONTROLS[d.capability.split('.')[0]]
    const offer = wants ? Object.keys(CONTROLS).filter(k => CONTROLS[k] === wants) : []
    return offer.length > 1 ? offer : []
  }
  const kinds = p.match(/^\/devices\/([^/]+)\/kinds$/)
  if (kinds) {
    const d = home.rooms.flatMap(r => r.devices).find(x => x.id === kinds[1])
    if (!d) { res.writeHead(404, { 'Content-Type': 'application/json' }); return res.end('{"detail":"unknown device"}') }
    const offer = offerFor(d)
    return json(res, { capability: d.capability, kind: kindOf(d), offer, words: Object.fromEntries(offer.map(k => [k, WORD[k]])),
                       why: offer.length ? 'This can be switched on and off, so it can be shown as anything that switches on and off. An alarm is the one that asks before it sounds.' : '' })
  }
  const setKind = p.match(/^\/devices\/([^/]+)\/kind$/)
  if (setKind && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => {
    const d = home.rooms.flatMap(r => r.devices).find(x => x.id === setKind[1])
    let k = null; try { k = JSON.parse(b).kind || null } catch {}
    if (d) d.kind = k && k !== d.capability ? k : null
    json(res, { ok: true, kind: d ? kindOf(d) : k })
  }) }
  if (req.method === 'POST' || req.method === 'DELETE') return json(res, { ok: true })   // forgetting a thing, or a phone leaving, answer like every other change
  let f = path.join(DIST, p === '/' ? 'index.html' : p)
  if (!fs.existsSync(f)) f = path.join(DIST, 'index.html')
  if (!fs.existsSync(f)) { res.writeHead(503, { 'Content-Type': 'text/plain' }); return res.end('No dist/ yet: run `npm run build` first, or use `BRAIN=http://localhost:' + PORT + ' npm run dev`.') }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' })
  fs.createReadStream(f).pipe(res)
})
/* The panel's live stream. It used to be held open and never written to, which was fine until a
   screen existed whose whole point is something happening in the room while you watch -- naming a
   switch by pressing it. Now anything the mock changes can be pushed the way the hub pushes it. */
const live = new Set()
function push(msg) { const s = JSON.stringify(msg); for (const sock of live) { try { sock.write(frame(s)) } catch { live.delete(sock) } } }
function frame(text) {
  const b = Buffer.from(text)
  const head = b.length < 126 ? Buffer.from([0x81, b.length])
    : Buffer.concat([Buffer.from([0x81, 126]), Buffer.from([b.length >> 8, b.length & 0xff])])
  return Buffer.concat([head, b])
}
// keep the websocket open; the panel shows Connected, and push() above sends when there is something to say
server.on('upgrade', (req, socket) => {
  if (/\/webrtc$/.test(req.url)) return socket.destroy()   // no WebRTC here either
  const key = req.headers['sec-websocket-key']
  const accept = crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64')
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n')
  live.add(socket)
  socket.on('close', () => live.delete(socket))
  socket.on('error', () => { live.delete(socket); })
})
server.listen(PORT, () => console.log(`mock brain on http://localhost:${PORT}/`))
