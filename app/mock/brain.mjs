/* A stand-in for the brain, for looking at the panel without a hub: serves ../dist and enough JSON for a lived-in
   house of eight rooms. `npm run mock`, then open http://localhost:8399/ (every ?at= ?wx= ?month= ?room= ?sheet= ?setup=
   preview works), or `BRAIN=http://localhost:8399 npm run dev` for hot reload against it.
   Knobs: PORT, WX=rainy (a condition), FOUND=0 (nothing new nearby), ENGINE=down (the engine-starting screen),
   LOCKED=1 (a code is set), FRESH=1 (first run), ASK=1 (a phone is asking to join; needs LOCKED=1), ?join=1 (the join screen),
   UPDATE=ready (one waiting, with its sheet), UPDATE=running (one happening, walking the phases), UPDATE=away (the sheet a
   phone outside the house gets). Nothing here talks to a real device; every POST or DELETE says ok. */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const DIST = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const PORT = Number(process.env.PORT || 8399)
const now = Math.floor(Date.now() / 1000)

const dev = (id, name, room_id, capability, state, attrs = {}, maker = null, more = {}) => ({ id, name, room_id, capability, state, attrs, maker, ...more })   // maker: what the registry knows, often nothing
/* a feature of a machine: a switch the brain took for an appliance from the unit's name (docs/kinds.md), with the unit it belongs to */
const feature = (id, name, room_id, state, hw, hw_name, maker = 'Samsung') => dev(id, name, room_id, 'switch', state, {}, maker, { guess: 'appliance', hw, hw_name })
const rooms = [
  { id: 'living', name: 'Living room', intent: 'movie', set_by: 'rule:evening-lights', hold_until: null, devices: [
    /* A bulb that can do color, IN a color, because until one existed here nobody saw that the
       panel was reading rgb_color off the wire and throwing it away: every light in this house
       was a warm white, so a magenta lamp and a 2700K one were the same picture and no test or
       screenshot could tell. color_mode is what says which it is -- rgb_color is reported in
       color_temp mode too, as the white point. See art.ts/bulbColor. */
    dev('l1', 'Ceiling light', 'living', 'light', 'on', { brightness: 90, color_mode: 'hs', rgb_color: [226, 72, 184], supported_color_modes: ['color_temp', 'hs'] }, 'Philips Hue'),
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
    feature('k7', 'Refrigerator Ice Maker', 'kitchen', 'on', 'hw-fridge', 'Refrigerator'),
    feature('k8', 'Refrigerator Ice Bites', 'kitchen', 'off', 'hw-fridge', 'Refrigerator'),
    feature('k9', 'Refrigerator Power Cool', 'kitchen', 'off', 'hw-fridge', 'Refrigerator'),
    feature('k10', 'Refrigerator Power Freeze', 'kitchen', 'on', 'hw-fridge', 'Refrigerator'),
    feature('k11', 'Dishwasher Sanitize', 'kitchen', 'off', 'hw-dw', 'Dishwasher'),
    feature('k12', 'Dishwasher Delay Start', 'kitchen', 'off', 'hw-dw', 'Dishwasher'),
    dev('k4', 'Kitchen speaker', 'kitchen', 'media', 'off', {}),
    dev('k5', 'Back door', 'kitchen', 'contact', 'off', {}),
    dev('k6', 'Humidity', 'kitchen', 'sensor.humidity', '51', { unit_of_measurement: '%' }),
  ] },
  { id: 'bedroom', name: 'Bedroom', intent: 'asleep', set_by: null, hold_until: null, devices: [
    dev('b1', 'Bedroom lamp', 'bedroom', 'light', 'off', { supported_color_modes: ['brightness'] }),
    dev('b2', 'Bedroom TV', 'bedroom', 'media', 'off', {}),
    /* a fan with a light in it: one fixture, the fan leading unless the owner says the light (docs/units.md) */
    dev('b3', 'Bedroom Fan', 'bedroom', 'fan', 'on', { percentage: 40, light: 'b5', leads: 'fan' }, 'Hunter', { hw: 'hw-fan', hw_name: 'Bedroom Fan', named_by_unit: true }),
    dev('b5', 'Bedroom Fan Light', 'bedroom', 'light', 'on', { brightness: 180, supported_color_modes: ['brightness'], fan: 'b3', leads: 'fan' }, 'Hunter', { hw: 'hw-fan', hw_name: 'Bedroom Fan', named_by_unit: true }),
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
    dev('y3', 'Walkway Pathlight Light', 'backyard', 'light', 'on', { motion: 'y4' }, 'Ring', { hw: 'hw-ring-wp', hw_name: 'Walkway Pathlight', named_by_unit: true }),   // its motion sensor is on its tile, not the strip
    dev('y4', 'Walkway Pathlight Motion', 'backyard', 'motion', 'on', {}, 'Ring', { hw: 'hw-ring-wp', hw_name: 'Walkway Pathlight', named_by_unit: true }),
  ] },
  { id: 'bath', name: 'Bathroom', intent: 'occupied', set_by: null, hold_until: null, devices: [] },
  { id: 'unassigned', name: 'New devices', intent: 'occupied', set_by: null, hold_until: null, devices: [
    /* The names are the ones a driver really gives, and the maker, the model and the account that
       brought each one are what the row has to tell them apart with before a room is picked. */
    dev('u1', 'Hue color lamp 1', 'unassigned', 'light', 'off', { supported_color_modes: ['hs'] }, 'Signify Netherlands B.V.', { model: 'Hue color lamp', entry: 'e-hue' }),
    dev('u2', 'Smart plug', 'unassigned', 'switch', 'off', {}, 'TP-Link Corporation Limited', { model: 'HS100' }),
    /* a Ring pathlight: a light and its motion sensor on one piece of hardware, one row on New devices (docs/units.md) */
    dev('u3', 'Garage Left Light Light', 'unassigned', 'light', 'off', { motion: 'u4' }, 'Ring', { hw: 'hw-ring-gl', hw_name: 'Garage Left Light', named_by_unit: true, model: 'Smart Lighting Pathlight', entry: 'e-ring' }),
    dev('u4', 'Garage Left Light Motion', 'unassigned', 'motion', 'off', {}, 'Ring', { hw: 'hw-ring-gl', hw_name: 'Garage Left Light', named_by_unit: true, model: 'Smart Lighting Pathlight', entry: 'e-ring' }),
  ] },
]
/* SWITCHES=11 fills New devices with a bridge's worth of look-alike wall switches -- the moment
   naming by touch exists for, and the one that cannot be judged with two rows in the list. Their
   names are the ones the bridge actually gives them, addresses and all, because that is the problem. */
const MESH = ['0004', '0005', '0006', '0008', '000a', '000b', '000e', '0010', '0011', '0014', '0016']
const unassigned = rooms.find(r => r.id === 'unassigned')
for (let i = 0; i < Number(process.env.SWITCHES || 0) && i < MESH.length; i++)
  unassigned.devices.push(dev(`mesh${MESH[i]}`, `Brilliant switch ${MESH[i]}`, 'unassigned', 'light', 'off', { brightness: 0, has_motion: true }, 'Brilliant', { model: 'Brilliant Smart Dimmer Switch' }))

/* A press, which is the whole mechanism: a switch announcing itself because a human touched it.
   POST /press or /press/<id> makes one happen; PRESS=1 rotates through them on its own so the
   screen can just be watched. Mock only -- on a hub this is the driver's own state event. */
let pressedId = null, pressedAt = 0
function pressEvent() {
  if (process.env.PRESS === '1' && !pressedId) { pressedId = unassigned.devices[0]?.id; pressedAt = Date.now() / 1000 }
  if (!pressedId || Date.now() / 1000 - pressedAt > 45) return []
  return [{ ts: pressedAt, kind: 'state', subject: pressedId, old: 'off', new: 'on', source: 'device', detail: null }]
}

/* A BIGGER HOUSE, on a knob. QUIET=n adds n rooms with one lamp off in each, which is what a real
   thirteen-room house looks like of an evening -- and the shape the Rooms tab's arrangement is
   hardest to get right at, since it is mostly index. design/rooms/Long.dc.html. */
for (let i = 0; i < Number(process.env.QUIET || 0); i++)
  rooms.splice(rooms.length - 1, 0, { id: `q${i}`, name: ['Theater', 'Basement', 'Main Workshop', 'Frontyard', 'Nadine\u2019s Room', 'Pod', 'Ace\u2019s Room', 'Loft', 'Porch', 'Attic', 'Landing', 'Utility'][i] ?? `Room ${i}`,
    intent: 'unknown', set_by: null, hold_until: null, devices: [dev(`qd${i}`, 'Lamp', `q${i}`, 'light', 'off')] })

const home = { name: "Temi's house", temp_unit: '°F', rooms }
const status = { driver: process.env.ENGINE === 'down' ? 'down' : 'ready', reason: process.env.ENGINE === 'down' ? "The hub's engine is not answering yet." : '',
  version: 'v0.3.0',   // the build this mock is: the panel reloads itself when a status answers with another (store.ts, newBuild)
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
/* An update waiting, and one happening. UPDATE=ready puts the nudge on Home and the sheet under
   This hub; UPDATE=running walks the phases so the wait can be looked at -- the several minutes where
   the house still works and the panel says what is being downloaded, and then the stretch where the
   brain is gone and the overlay counts down. docs/updates.md, piece 6. */
const waiting = { version: 'v0.3.1', sha: 'b'.repeat(40), when: new Date().toISOString(), title: 'Quieter mornings',
                  what: ['Speakers remember how loud you had them.', 'The kitchen comes up on the wall faster.'] }
if (process.env.UPDATE) {
  status.update = { version: 'v0.3.0', commit: 'abc123def456', channel: 'release', latest: waiting, whats_new: null,
                    held: false, reached_us: true, available: true, offer: true, rejected: null, auto: true,
                    verified: true, checked: Date.now() / 1000, requested: process.env.UPDATE === 'running',
                    state: process.env.UPDATE === 'running' ? { state: 'running', started: Date.now() / 1000 } : null,
                    error: null, progress: null, seconds: 260, dark_seconds: 45 }
}
/* The phases, a few seconds apart, so the panel can be watched moving through them rather than
   described. The last one is dark on purpose: that is where the countdown takes over. */
if (process.env.UPDATE === 'running') {
  const walk = [['checking', 'Checking this update is really ours.', false, 1],
                ['fetching', 'Fetching the new version.', false, 2],
                ['downloading', 'Downloading it.', false, 3],
                ['restarting', 'Restarting the house.', true, 4]]
  let i = 0
  const step = () => {
    const [phase, says, dark, n] = walk[i]
    status.update.progress = { phase, says, at: Date.now() / 1000, since: 0, dark, step: n, steps: 5, detail: null,
                               moving: phase === 'restarting' ? ['brain', 'homeassistant'] : null,
                               notices: phase === 'restarting' ? ['For about a minute the wall switches still work but the app doesn\u2019t.'] : [] }
    push({ type: 'status', status })     // the real brain tells the panel the moment the phase changes
    if (++i < walk.length) setTimeout(step, 6000)
  }
  setTimeout(step, 2000)
}
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
  look: { feel: process.env.FEEL || 'nightfall', tone: process.env.TONE || 'follow', face: process.env.FACE || 'glass', layout: process.env.LAYOUT || 'auto', nav: process.env.NAV || 'auto' } }   // the default a fresh house gets; FEEL=calm LAYOUT=rail TONE=pastel NAV=top FACE=paper start it somewhere else
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
/* The one pairing session a hub can have. It is a clock, not a machine: a few seconds after the door
   opens something joins, and a second later it is a device in the house with no room. */
let pairing = null
function pairStatus() {
  if (!pairing) return { state: 'idle' }
  if (pairing.state !== 'listening') return { ...pairing, at: undefined, joined: undefined }
  const on = (Date.now() - pairing.at) / 1000
  if (process.env.PAIR === 'none') {
    if (on > 12) { pairing = { state: 'closed', text: 'Nothing joined. Put the device in pairing mode and try again.' }; return pairing }
    return { state: 'listening', text: 'Listening. Put the device in pairing mode.', seconds_left: Math.round(12 - on) }
  }
  if (process.env.PAIR === 'pin' && on > 4 && pairing.needs !== null) {
    pairing.needs = 'pin'
    return { state: 'pin', needs: 'pin', text: 'It is a secured device and wants the 5-digit code on its sticker.' }
  }
  if (pairing.joined === undefined && on > 5) pairing.joined = Date.now()
  if (pairing.joined === undefined) return { state: 'listening', text: 'Listening. Put the device in pairing mode.', seconds_left: Math.round(240 - on) }
  if (Date.now() - pairing.joined < 2500) return { state: 'found', text: 'Something is joining… (Smart plug)', device: { id: 'new-plug', name: 'Smart plug' } }
  /* it is in: the house gains it, once, with no room of its own */
  if (!unassigned.devices.some(d => d.id === 'radio-new')) {
    const d = dev('radio-new', 'Smart plug', 'unassigned', 'plug', 'off', {})
    unassigned.devices.push(d)
    push({ type: 'device', device: d })
  }
  pairing = { state: 'done', text: 'A plug joined the house.', device: { id: 'new-plug', name: 'Smart plug' } }
  return pairing
}

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
  // A bridge that never came back (docs/network.md, piece 6). The recovery is a walk to a socket, so
  // it is in the sentence; the one button is the only thing the panel can actually perform.
  { kind: 'bridge', subject: 'c8ebba', name: 'The Hallway bridge', where: 'Hallway', since: now - 86400,
    text: 'The Hallway bridge hasn’t been heard from since the Wi‑Fi changed to Downstairs. Its switches still work on the wall — the hub just can’t see them. Plug it into the hub for a minute to set it right.',
    acts: [{ do: 'It’s gone, remove it', act: 'bridge', to: 'c8ebba', yes: 'Yes, remove it', no: 'Keep it',
             ask: 'Remove the Hallway bridge? Its switches stop appearing on the panel; they keep working on the wall.' }] },
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

/* What this house shares, and who holds it. The door is open while nothing holds it yet (a bridge
   waiting to be scanned) or for five minutes after Add an app. */
const share = {
  on: !!process.env.SHARED,
  kinds: ['light', 'switch', 'appliance'],
  locks: false,
  offer: ['light', 'switch', 'appliance'],
  holders: process.env.SHARED === 'held' ? [{ index: 1, name: 'Apple Home' }] : [],
  opened: 0,
  left_out: [],
  stopped: false,   // SHARED=stopped, or POST {stopped:true}: the bridge container is not there
}
/* Three of the house's own things for the map at the top of the Share page, with the ids the pane
   posts so that keeping one home takes it out of the picture here too. */
const SAMPLE = [
  { id: 'k1', name: 'Kitchen lights', kind: 'light' },
  { id: 'l1', name: 'Ceiling light', kind: 'light' },
  { id: 'kettle', name: 'Kettle', kind: 'switch' },
]
function shareState() {
  const left = share.opened ? Math.max(0, Math.round((share.opened + 300000 - Date.now()) / 1000)) : 0
  const waiting = share.on && !share.stopped && !share.holders.length
  return {
    ready: true, on: share.on, kinds: share.kinds, locks: share.locks, offer: share.offer,
    shared: share.on ? Math.max(0, share.kinds.length * 3 - share.left_out.length) : 0, candidates: share.kinds.length * 3,
    left_out: share.left_out, left_out_now: share.on ? share.left_out.length : 0, holders: share.holders,
    // Filtered by what is kept home, the way the brain's own preview is: it comes off candidates(),
    // so a lamp left out is absent from the picture for the same reason it is absent from the list.
    preview: SAMPLE.filter(d => !share.left_out.includes(d.id) && share.kinds.includes(d.kind))
      .slice(0, 3).map(({ name, kind }) => ({ name, kind })),
    open: share.on && !share.stopped && (waiting || left > 0),
    seconds_left: share.holders.length ? left : null,
    code: share.on && (waiting || left > 0) ? '0033-033-8072' : null,
    bridge: { running: share.on && !share.stopped, commissioned: !!share.holders.length, stale: !!share.stopped, error: null },
  }
}
const phones = { phones: [
  { id: 'w', name: 'This wall', kind: 'wall', joined: now - 86400 * 30, expires: null, remote: false, last_seen: now, how: 'setup', me: true },
  { id: 'p1', name: "Temi's iPhone", kind: 'phone', joined: now - 86400 * 20, expires: null, remote: false, last_seen: now - 3600, how: 'code', me: false },
  { id: 'p2', name: "Nadine's Android phone", kind: 'phone', joined: now - 3600, expires: now + 86400 * 2, remote: false, last_seen: now - 600, how: 'wall', me: false },
], asks: process.env.ASK ? [{ id: 'a1', name: "Sam's iPhone", kind: 'phone', asked: now - 30 }] : [] }

/* ---------- a bridge being set up ----------
   The real brain watches a thing on a cable; this walks a clock, so the sheet can be seen moving.
   BRIDGE=cable starts at the knock and runs the whole way; the other values pin one moment. */
const BRIDGE = process.env.BRIDGE || ''
/* Bridges running older software than the house ships (docs/puck-updates.md). BEHIND=1 is one the hub
   can name by its room, BEHIND=2 two of them, BEHIND=anon one it cannot honestly place. */
const BEHIND = {
  '1': [{ chip: 'c8ebba', room: 'Hallway', fw: '0.2.0', latest: '0.3.1', online: true }],
  '2': [{ chip: 'c8ebba', room: 'Hallway', fw: '0.2.0', latest: '0.3.1', online: true },
        { chip: 'f4a9f3', room: 'Landing', fw: '0.2.0', latest: '0.3.1', online: false }],
  anon: [{ chip: 'c8ebba', room: null, fw: '0.2.0', latest: '0.3.1', online: true }],
}[process.env.BEHIND || ''] || []
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
  if (BRIDGE !== 'cable' && !bridgeAt) {   // a pinned moment, until something moves it on
    return {
      knocking: { state: 'knocking', how: 'air' },
      working: { state: 'working', how: 'cable', step: 'keys' },
      placing: { state: 'placing', how: 'cable', switches: 11, signal: 'strong' },
      ready: { state: 'ready', how: 'cable', switches: 11, unplaced: 8 },
      // The two shapes of the same question. BRIDGE=wifi is a hub on a cable, which has to be told
      // the whole thing; BRIDGE=wifi-known is a hub standing on the network, which knows the name and
      // wants only the password -- the common case, and the one that used to ask for both.
      wifi: { state: 'failed', how: 'cable', needs: 'wifi',
              text: 'The hub does not know the house\u2019s Wi\u2011Fi yet \u2014 it is on a cable itself. Tell it once, under This hub, and every bridge after this one just works.' },
      'wifi-known': { state: 'failed', how: 'cable', needs: 'wifi', ssid: 'VirusBroadcast',
                      text: 'The hub is on VirusBroadcast. It needs the password for it once \u2014 then this bridge, and every one after it, just works.' },
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
  /* Install: on a hub the brain restarts and comes back as the next build, and the page follows it
     (store.ts, newBuild). The mock only takes the request; the e2e speaks the new version itself. */
  if (p === '/update' && req.method === 'POST') { if (status.update) status.update.requested = true; return json(res, status.update ?? {}) }
  if (p === '/update/check' && req.method === 'POST') { if (status.update) status.update.checked = Date.now() / 1000; return json(res, status.update ?? {}) }
  if (p === '/update/notes/seen' && req.method === 'POST') { if (status.update) status.update.whats_new = null; return json(res, status.update ?? {}) }
  /* Turning it off and on again. The sheet's every word is the brain's, so the mock has to speak them
     or This hub previews a blank question. RESTART=weary shows the rung that has stopped helping, and
     the POST answers and does nothing: the panel's overlay is the thing being looked at here. */
  /* What installing would cost, in this house. Half of it is the restart sheet's answer to the same
     question, and the mock says it the same way for the same reason: This hub would otherwise
     preview a blank question. */
  if (p === '/update/ask') {
    const secs = status.update?.seconds ?? 300, dark = status.update?.dark_seconds ?? 60
    return json(res, {
      version: waiting.version, title: `Install ${waiting.version}?`, yes: 'Install it', what: waiting.what,
      seconds: secs, how_long: `about ${Math.round(secs / 60)} minutes`,
      dark_seconds: dark, dark_how_long: `about ${Math.round(dark / 10) * 10} seconds`,
      keeps: 'Lights and switches keep working, and so does everything else while it downloads.',
      stops: ['Motion lights and schedules pause.'], flight: [], blocked: null,
      warn: process.env.UPDATE === 'away' ? 'Nobody is home if it doesn\u2019t come back. The hub puts the old version back by itself, but the house is away for a few minutes while it does.' : null,
      auto: true,
    })
  }
  if (p === '/restart' && req.method !== 'POST') {
    const rung = url.searchParams.get('rung') || 'hub'
    const secs = { hub: 30, everything: 120, machine: 180 }[rung] ?? 30
    const weary = process.env.RESTART === 'weary'
    return json(res, {
      rung, title: { hub: 'Restart the hub?', everything: 'Restart everything?', machine: 'Restart the little computer?' }[rung],
      yes: { hub: 'Restart the hub', everything: 'Restart everything', machine: 'Restart the little computer' }[rung],
      keeps: rung === 'hub' ? 'Lights and switches keep working.' : 'Switches on the wall keep working.',
      stops: rung === 'hub' ? ['Motion lights and schedules pause.'] : ['Everything the hub talks to goes quiet until it\u2019s back \u2014 lights, sensors and the radios.'],
      flight: [], seconds: secs, how_long: secs < 90 ? `about ${secs} seconds` : `about ${Math.round(secs / 60)} minutes`,
      blocked: null, busy: false, lately: weary ? 3 : 0,
      harder: weary ? (rung === 'hub' ? 'everything' : 'machine') : null,
      weary: weary ? 'The hub has restarted 3 times in the past hour. Something is wrong that restarting isn\u2019t fixing.' : null,
      warn: null, may: true,
    })
  }
  if (p === '/restart' && req.method === 'POST') return json(res, { rung: 'hub', seconds: 30, how_long: 'about 30 seconds' })
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
/* The bridges This hub lists, and what a household can change about one (docs/puck-light.md).
   BRIDGES=none empties the list, so the page can be seen without one. */
const bridgeRows = process.env.BRIDGES === 'none' ? [] : [
  { chip: 'c8ebba', room: 'hall', where: 'Hallway', online: true, signal: 'strong', switches: 11,
    fw: '0.5.0', behind: false, shipped: '0.5.0', night: true, level: 110, lift: false },
  { chip: 'f4a9f3', room: 'landing', where: 'Landing', online: true, signal: 'weak', switches: 4,
    fw: '0.4.0', behind: true, shipped: '0.5.0', night: false, level: 110, lift: false },
  { chip: '9a01cc', room: null, where: 'A bridge', online: true, signal: 'none', switches: 0,
    fw: '0.3.1', behind: false, shipped: null, night: null, level: null, lift: false },
  { chip: 'd21e04', room: null, where: 'A bridge', online: false, signal: 'none', switches: 0,
    fw: '0.5.0', behind: false, shipped: '0.5.0', night: null, level: null, lift: false },
]
  if (p === '/bridge/list') return json(res, { bridges: bridgeRows })
  if (p === '/bridge/light' && req.method === 'POST') { let raw = ''; req.on('data', c => (raw += c)); return req.on('end', () => {
    let b = {}; try { b = JSON.parse(raw) } catch {}
    const row = bridgeRows.find(x => x.chip === b.chip)
    if (!row) return json(res, { error: 'The hub does not know that bridge.' }, 400)
    if (b.night !== undefined) row.night = !!b.night
    if (b.level !== undefined && row.night) row.level = b.level
    if (b.lift !== undefined) row.lift = !!b.lift
    json(res, { bridges: bridgeRows })
  }) }
  if (p === '/bridge/forget') return json(res, { forgotten: 'The Hallway bridge' })
  if (p === '/health') return json(res, { notes })
  /* What happened, and who changed what. The brain measures these off the event log (happened.py);
     here they are fixed, so the page can be drawn and argued about without a house that has actually
     been left alone all day. The wording is the brain's in production and copied here verbatim --
     including the group headings, which is the whole point of them coming over the wire. */
  if (p === '/happened') return json(res, {
    lede: 'You were out from 9:04am until 6:12pm. Two things are still on that were on the whole time.',
    since: Date.now() / 1000 - 10 * 3600, hint: '2 things still on', empty: false,
    away: { from: Date.now() / 1000 - 9.2 * 3600, to: Date.now() / 1000 - 0.3 * 3600 },
    groups: [
      { id: 'still', label: 'Still on', items: [
        { kind: 'still', subject: 'l1', seconds: 36000, ts: Date.now() / 1000 - 10 * 3600, word: 'on', when: 'now',
          text: 'Ceiling light has been on for 10 hours, since 7:32am.', where: 'Living room · a light',
          acts: [{ do: 'Turn off', act: 'device', to: 'l1', arg: 'off' }] },
        { kind: 'still', subject: 'k1', seconds: 32400, ts: Date.now() / 1000 - 9 * 3600, word: 'on', when: 'now',
          text: 'Kitchen lights have been on for 9 hours, since 9:10am.', where: 'Kitchen · a light',
          acts: [{ do: 'Turn off', act: 'device', to: 'k1', arg: 'off' }] },
      ] },
      { id: 'over', label: 'While you were out', items: [
        { kind: 'over', subject: 'f1', seconds: 27420, ts: Date.now() / 1000 - 12 * 3600, word: 'unlocked', when: 'last night',
          text: 'Front door was unlocked for 7 hours overnight, 11:03pm to 6:40am. It is locked now.',
          where: 'Front door · a lock', acts: [] },
        { kind: 'over', subject: 'cover.garage', seconds: 7200, ts: Date.now() / 1000 - 5 * 3600, word: 'open', when: '1:12pm',
          text: 'Garage door was open for 2 hours, 1:12pm to 3:12pm. It is closed now.',
          where: 'Garage · a blind', acts: [] },
      ] },
      { id: 'people', label: 'People and phones', items: [
        { kind: 'phone', subject: 'p1', ts: Date.now() / 1000 - 3 * 86400, when: 'Tuesday',
          text: "Ada's iPad joined the house.", acts: [] },
        { kind: 'phone', subject: 'p2', ts: Date.now() / 1000 - 5 * 86400, when: 'Sunday',
          text: "Sam's phone's stay ended on its own.", acts: [] },
      ] },
    ],
  })
  if (p.startsWith('/happened/changes')) return json(res, {
    coded_since: Date.now() / 1000 - 16 * 86400, coded_when: 'Sep 4', more: false,
    rows: [
      { who: "Temi's iPhone", named: true, kind: 'home', subject: 'hallway', when: '4:02pm', ts: 0, text: 'renamed Hallway to Landing.' },
      { who: 'Someone at the wall', named: false, kind: 'draft', subject: 'r1', when: 'Wednesday', ts: 0, text: 'approved a suggested routine.' },
      { who: 'Someone at the wall', named: false, kind: 'phone', subject: 'p1', when: 'Tuesday', ts: 0, text: "let Ada's iPad into the house, for good." },
      { who: "Ada's iPad", named: true, kind: 'phone', subject: 'p3', when: 'Tuesday', ts: 0, text: 'asked to join the house.' },
      { who: "Temi's iPhone", named: true, kind: 'home', subject: 'e1', when: 'Tuesday', ts: 0, text: 'removed the Nest. Everything it brought went with it.' },
      { who: "Temi's iPhone", named: true, kind: 'home', subject: 'l1', when: 'Tuesday', ts: 0, text: 'now treats Ceiling light as a light.' },
      { who: "Ada's iPad", named: true, kind: 'share', subject: 'device', when: 'Monday', ts: 0, text: 'shared Kitchen lights with other apps.' },
      { who: 'The hub', named: false, kind: 'bridge', subject: 'c8ebba', when: 'Monday', ts: 0, text: 'recognized the bridge c8ebba.' },
      { who: 'The hub', named: false, kind: 'home', subject: 'driver', when: 'Sep 13', ts: 0, text: 'signed in to Messages.' },
      { who: 'The hub', named: false, kind: 'home', subject: 'update', when: 'Sep 12', ts: 0, text: 'installed 0.8.1.' },
    ],
  })
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
  /* Blinking a thing so the person in the room can see which row it is. The real brain drives the
     driver three times over (api.py, identify_device); here it flips the state so the panel's own
     tiles move, and answers with the same sentence the hub answers with. */
  if (p.startsWith('/devices/') && p.endsWith('/identify') && req.method === 'POST') {
    const id = decodeURIComponent(p.split('/')[2])
    const d = rooms.flatMap(r => r.devices).find(x => x.id === id)
    if (!d) return json(res, { detail: 'unknown device' }, 404)
    const was = d.state, bright = d.attrs?.brightness
    let n = 0
    const step = () => {
      d.state = n % 2 ? 'off' : 'on'
      if (d.attrs && bright !== undefined) d.attrs.brightness = d.state === 'on' ? 254 : 0
      push({ type: 'device', device: d })
      if (++n < 6) return setTimeout(step, n % 2 ? 450 : 600)
      d.state = was
      if (d.attrs && bright !== undefined) d.attrs.brightness = bright
      push({ type: 'device', device: d })
    }
    step()
    return setTimeout(() => json(res, { ok: true, text: 'Blinked three times. If you saw nothing, it is in another room — or it has no lamp on it.' }), 3150)
  }
  if (p === '/drivers/zwave/retry' && req.method === 'POST') return json(res, { ok: true, drivers: status.drivers })
  if (p === '/flows/r1') {
    if (req.method !== 'POST') return json(res, signIn)
    const i = notes.findIndex(n => n.acts?.some(a => a.to === 'r1')); if (i >= 0) notes.splice(i, 1)   // answered: the line on Home goes
    return json(res, { type: 'create_entry', flow_id: 'r1', handler: 'nest', kind: 'Google Nest', entry_title: 'home-hub' })
  }
  if (p === '/catalog') return json(res, catalog)
  /* The network the house runs on (docs/network.md, design/network/).
       NET=cable    the hub is on ethernet and eleven bridges are on a Wi-Fi it was told about
       NET=wifi     the hub is on the Wi-Fi too, and a change takes it with them
       NET=moved    the hub has moved and the password it holds is for somewhere else
       NET=none     no host script at all ('unknown'): the row says so and offers two typed fields
       NET=off      a managed hub with a radio and nothing connected. Looks like 'none' and is the
                    opposite case: this one IS the hub that should be moved
     MOVE=moving|done|late pins a moment of the move instead of walking it. */
  if (p.startsWith('/network')) return network(p, req, res)
  /* A bridge being set up. BRIDGE=cable walks the whole job the way a real one does -- software,
     Wi-Fi, keys, then the walk to find it a socket -- so the sheet can be watched rather than
     described. BRIDGE=knocking|working|placing|ready|failed pins one moment instead. */
  if (p === '/bridge') return json(res, { ...bridgeNow(), ...(netMove ? { moving: netMove } : {}) , ...(BEHIND.length ? { behind: BEHIND } : {}) })
  /* What the bridge can hear, and whose side each one is on. NEARBY=n sets how many are unclaimed;
     NEARBY=0 with SPOKEN=1 is the case the Waiting board draws -- nothing to let in, but something
     nearby that has to be started over first, which looks identical to an empty room to a scan. */
  if (p === '/bridge/nearby') {
    const free = Number(process.env.NEARBY ?? 2), spoken = Number(process.env.SPOKEN ?? 0)
    const one = (i, st) => ({ state: st, rssi: -45 - i * 12, addr: `AA:BB:${10 + i}`,
                              ...(st === 'unclaimed' ? { uuid: String(i).repeat(32).slice(0, 32) } : { net: 'ab'.repeat(8) }) })
    const waiting = Array.from({ length: free }, (_, i) => one(i, 'unclaimed'))
    const other = Array.from({ length: spoken }, (_, i) => one(free + i, 'other'))
    const text = free === 1 ? 'One switch is waiting to be let in.'
      : free > 1 ? `${free} switches are waiting to be let in.`
      : other.length ? 'Nothing is asking to be let in, but there is a switch nearby that is on another network. That one has to be started over first.'
      : 'Nothing nearby is asking to be let in.'
    return json(res, { state: 'done', waiting, claimed_elsewhere: other, text })
  }
  /* Blinking one of them. BLINK=fail is a switch that cannot be reached, which matters because the
     blink IS the identity check when there is no code -- a failure means the next question cannot
     honestly be asked. */
  if (p === '/bridge/blink' && req.method === 'POST') {
    return process.env.BLINK === 'fail'
      ? json(res, { state: 'failed', text: 'The bridge could not reach that switch.' })
      : json(res, { state: 'done' })
  }
  /* Letting a new switch in: the phone sends whatever its camera read, whole, or a bare uuid when
     the code is behind the plate. */
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
    if (what === 'wifi') { bridgeAt = Date.now(); bridgePinned = null }        // told: the job carries on
    return json(res, bridgeNow())
  }
  /* PAIRING a radio thing, simulated so the screens that drive it can be seen. The panel opens a door,
     something joins a few seconds later, and the house gains a device with no room -- which is what
     beat four then asks about. PAIR=pin makes it ask for a lock's code first; PAIR=none lets the
     window run out with nothing joining; PAIR=fail refuses at the door. */
  if (p === '/pair' && req.method === 'POST') {
    if (process.env.PAIR === 'fail') { pairing = { state: 'failed', text: 'That radio is not answering.' }; return json(res, pairing) }
    pairing = { state: 'listening', at: Date.now(), text: 'Listening. Put the device in pairing mode.' }
    return json(res, pairStatus())
  }
  if (p === '/pair' && req.method === 'DELETE') { pairing = { state: 'closed', text: 'Stopped.' }; return json(res, pairing) }
  if (p === '/pair/pin' && req.method === 'POST') {
    if (!pairing || pairing.needs !== 'pin') { res.writeHead(400, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ detail: 'Nothing is asking for a code right now.' })) }
    pairing.needs = null; pairing.joined = Date.now()
    return json(res, pairStatus())
  }
  if (p === '/pair') return json(res, pairStatus())
  if (p === '/assistant') return json(res, { available: true, configured: false, source: null, model: 'claude-sonnet-5' })
  if (p === '/setup/drivers') return json(res, status)
  if (p === '/setup/advanced') return json(res, { url: 'http://hub.local:8123/', username: 'hub', password: 'secret' })
  if (/^\/rooms\/[^/]+\/why/.test(p)) return json(res, why)
  if (p === '/suggestions') return json(res, { items: [
    { id: 'u3', name: 'Garage Left Light', room: 'backyard', why: 'the same unit as Walkway Pathlight Light', source: 'house' },
    { id: 'u1', name: 'Color lamp', room: 'living', why: 'the same unit as the floor lamp', source: 'assistant' },
    { id: 'u2', name: 'Plug', room: '', why: 'a plainer name', source: 'house' }], assistant: true })
  if (p === '/phone') return json(res, { ip: '192.168.1.40' })
  if (p === '/phones/me') return json(res, { locked: !!process.env.LOCKED, paired: true, home: 'Main Palace', phone: null })
  if (p === '/phones') return json(res, phones)
  /* the accounts page: one of each state, so the page can be read without a house behind it.
     ACCOUNTS=0 empties it (the nothing-signed-in-yet case). */
  if (p === '/accounts') return json(res, { accounts: process.env.ACCOUNTS === '0' ? [] : [
    { id: 'e-nest', kind: 'Google Nest', name: 'Google Nest', state: 'signin', why: '', flow: 'r1', things: 4 },   // r1 is the one flow the mock can actually walk, so Sign in again works here
    { id: 'e-ring', kind: 'Ring', name: 'Ring', state: 'stopped', why: 'the key it was given has been revoked', flow: null, things: 3 },
    { id: 'e-hue', kind: 'Philips Hue', name: 'Philips Hue bridge', state: 'on', why: '', flow: null, things: 11 },
    { id: 'e-tesla', kind: 'Tesla', name: 'Tesla', state: 'on', why: '', flow: null, things: 1 },
  ] })
  /* Sharing the house outward (docs/matter.md). Held in memory so the switches on This hub actually
     move, the door opens, and a code appears -- SHARED=on starts with it already shared, and
     SHARED=held with an app holding it, which is the state the screen is hardest to get right in. */
  if (p === '/share' && req.method === 'GET') return json(res, shareState())
  if (p === '/share' && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => {
    let body = {}; try { body = JSON.parse(b) } catch {}
    if (body.on != null) share.on = !!body.on
    if (body.kinds) share.kinds = body.kinds.filter(k => share.offer.includes(k))
    if (body.locks != null) share.locks = !!body.locks
    if (body.stopped != null) share.stopped = !!body.stopped
    if (body.left_out) share.left_out = body.left_out
    json(res, shareState())
  }) }
  if (/^\/devices\/[^/]+\/share$/.test(p) && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => {
    const id = decodeURIComponent(p.split('/')[2])
    let wanted = false; try { wanted = !!JSON.parse(b).shared } catch {}
    share.left_out = wanted ? share.left_out.filter(x => x !== id) : [...new Set([...share.left_out, id])]
    json(res, shareState())
  }) }
  if (p === '/share/window' && req.method === 'POST') {
    if (share.stopped) { res.writeHead(409, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ detail: 'The part of the hub that talks to other apps is not running, so there is nothing to open yet.' })) }
    share.opened = Date.now(); return json(res, shareState())
  }
  if (p === '/share/qr.svg') { res.writeHead(200, { 'Content-Type': 'image/svg+xml' }); return res.end(FAKE_QR) }
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
  const kindOf = d => (d.kind || d.guess || d.capability).split('.')[0]
  const CONTROLS = { light: 'onoff', switch: 'onoff', fan: 'onoff', alarm: 'onoff', appliance: 'onoff', media: 'onoff+playing', climate: 'temperature', vacuum: 'errand', camera: 'picture' }
  const WORD = { light: 'Light', switch: 'Plug', fan: 'Fan', alarm: 'Alarm', appliance: 'Appliance', media: 'Speaker', climate: 'Thermostat', vacuum: 'Vacuum', camera: 'Camera' }
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
                       why: offer.length ? 'This can be switched on and off, so it can be shown as anything that switches on and off. A plug goes off with Everything off; an appliance is part of a machine and is left alone. An alarm is the one that asks before it sounds.' : '' })
  }
  const setLead = p.match(/^\/devices\/([^/]+)\/lead$/)
  if (setLead && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => {
    let k = 'fan'; try { k = JSON.parse(b).lead || 'fan' } catch {}
    const d = home.rooms.flatMap(r => r.devices).find(x => x.id === setLead[1])
    for (const x of home.rooms.flatMap(r => r.devices)) if (d && x.hw && x.hw === d.hw) x.attrs.leads = k
    json(res, { ok: true, leads: k })
  }) }
  const setKind = p.match(/^\/devices\/([^/]+)\/kind$/)
  if (setKind && req.method === 'POST') { let b = ''; req.on('data', c => (b += c)); return req.on('end', () => {
    const d = home.rooms.flatMap(r => r.devices).find(x => x.id === setKind[1])
    let k = null; try { k = JSON.parse(b).kind || null } catch {}
    if (d) d.kind = k && k !== (d.guess || d.capability) ? k : null   // the way back is what it would be shown as anyway
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

/* ---- the network, and eleven bridges following it ---------------------------------------- */
const NET = process.env.NET ?? 'cable'
const ROOMS = ['Kitchen', 'Living room', 'Landing', 'Hallway', 'Back bedroom', 'Study',
               'Bathroom', 'Porch', 'Garage', 'Dining room', 'Spare room']
let netMove = process.env.MOVE ? seedMove(process.env.MOVE) : null
let netSsid = 'Upstairs'

function seedMove(which) {
  if (which === 'moving') return { state: 'moving', ssid: 'Downstairs', total: 11, followed: ROOMS.slice(0, 3), waiting: ROOMS.slice(3) }
  if (which === 'late') return { state: 'done', ssid: 'Downstairs', total: 11, followed: ROOMS.slice(0, 9), late: ['The hallway', 'The back bedroom'] }
  return { state: 'done', ssid: 'Downstairs', total: 11, followed: ROOMS }
}

function netState() {
  // Mirrors bridge.wifi_for_pucks(): a hub on Wi-Fi hands out the network it is ON, and when that is
  // not the one it holds a password for, `known` goes false and the name is the hub's, not the old one.
  const moved = NET === 'moved'
  const bridges = { ssid: moved ? 'Downstairs' : netSsid, checked: NET === 'wifi' || moved, known: !moved, count: 11 }
  if (NET === 'wifi') return { how: 'wifi', ssid: netSsid, signal: 'strong', band: '5', ip: '192.168.1.30', name: 'hub', can_change: true, managed: true, bridges, bridges_moving: netMove }
  if (NET === 'moved') return { how: 'wifi', ssid: 'Downstairs', signal: 'ok', ip: '192.168.1.30', name: 'hub', can_change: true, managed: true, bridges, bridges_moving: netMove }
  if (NET === 'off') return { how: 'none', ip: '127.0.0.1', name: 'hub', can_change: true, managed: true, bridges, bridges_moving: netMove }
  if (NET === 'none') return { how: 'unknown', ip: '192.168.1.9', name: 'hub', can_change: false, managed: false, bridges, bridges_moving: netMove }
  return { how: 'cable', ip: '192.168.1.9', name: 'hub', can_change: true, spare: null, managed: true, bridges, bridges_moving: netMove }
}

function network(p, req, res) {
  if (p === '/network') return json(res, netState())
  if (p === '/network/scan') return json(res, { can_change: NET !== 'none', networks: [
    { ssid: 'Downstairs', signal: 'strong', band: '5', secure: true },
    { ssid: 'BT-HUB-9QK2', signal: 'faint', band: '2.4', secure: true },
    { ssid: 'Flat 3 guest', signal: 'faint', band: '2.4', secure: false },
  ] })
  if (p === '/network/done') { netMove = null; return json(res, bridgeNow()) }
  // Moving them over, one every second and a half, so the sheet can be watched rather than described.
  let raw = ''
  req.on('data', c => (raw += c))
  return req.on('end', () => {
    let b = {}
    try { b = JSON.parse(raw) } catch {}
    netSsid = b.ssid || 'Downstairs'
    netMove = { state: 'moving', ssid: netSsid, total: 11, followed: [], waiting: [...ROOMS] }
    const late = process.env.MOVE === 'late'
    const tick = setInterval(() => {
      if (!netMove || netMove.state === 'done') return clearInterval(tick)
      const left = late ? 2 : 0
      if (netMove.waiting.length > left) netMove.followed.push(netMove.waiting.shift())
      else {
        netMove = { state: 'done', ssid: netSsid, total: 11, followed: netMove.followed,
                    ...(left ? { late: ['The hallway', 'The back bedroom'] } : {}) }
        clearInterval(tick)
      }
    }, 1500)
    json(res, netMove)
  })
}
