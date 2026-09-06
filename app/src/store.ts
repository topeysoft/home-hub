import { reactive } from 'vue'
import { getHome, getEvents, getAmbient, getScenes, getStatus, getDiscovered, connect, act, setIntent, setHomeIntent, type Room, type Device, type Home, type Event, type Ambient, type Rules, type Status, type Found, type Intent } from './api'
import { sunPosition, sunGuess, moonPhase } from './sun'

export const store = reactive({
  rooms: [] as Room[], linkUp: false, linkLost: false, error: '', loaded: false,   // linkLost: down long enough to be worth mentioning
  toast: null as null | { id: number; text: string; kind: 'info' | 'error' },
  pending: {} as Record<string, true>,     // devices waiting for the house to confirm a change
  viewer: null as Device | null,            // camera shown full screen
  events: [] as Event[],
  ambient: { location: null, weather: null } as Ambient,
  ambientLoaded: false,
  rules: {} as Rules,                        // scene rules from the brain, to tell whether a room still matches its scene
  sheet: (['location', 'add'].includes(new URLSearchParams(location.search).get('sheet') ?? '') ? new URLSearchParams(location.search).get('sheet') : null) as null | 'location' | 'add',   // the two soft sheets the panel has; ?sheet=location previews one
  status: null as Status | null,            // where the hub is in its life: engine down, fresh, ready; and whether setup finished
  homeName: '' as string,
  found: [] as Found[],                      // things noticed on the network that are not set up yet
  sky: { elevation: -20, azimuth: 0, phase: 0, hour: 0, condition: 'clear-night', guessed: true },   // what the sky draws
})

/* ---------- the sky: sun from the clock and the location, weather from the house ---------- */
const params = new URLSearchParams(location.search)
const previewAt = params.get('at')          // ?at=18:30 previews an hour of the day
const previewWx = params.get('wx')          // ?wx=rainy previews a condition
export const WEATHER_LABEL: Record<string, string> = {
  sunny: 'Clear', 'clear-night': 'Clear', partlycloudy: 'Partly cloudy', cloudy: 'Cloudy', fog: 'Fog', rainy: 'Rain', pouring: 'Heavy rain',
  hail: 'Hail', lightning: 'Storm', 'lightning-rainy': 'Thunderstorm', snowy: 'Snow', 'snowy-rainy': 'Sleet', windy: 'Windy', 'windy-variant': 'Windy', exceptional: 'Unusual weather',
}
export function updateSky() {
  const now = new Date()
  if (previewAt) { const [h, m] = previewAt.split(':').map(Number); now.setHours(h || 0, m || 0, 0, 0) }
  const loc = store.ambient.location
  const sun = loc ? sunPosition(now, loc.lat, loc.lon) : sunGuess(now)
  const condition = previewWx ?? store.ambient.weather?.condition ?? (sun.elevation < -6 ? 'clear-night' : 'sunny')
  store.sky = { ...sun, phase: moonPhase(now), hour: now.getHours() + now.getMinutes() / 60, condition, guessed: !loc }
}
export function weatherLine(): string {
  const w = store.ambient.weather
  if (!w && !previewWx) return ''
  const label = WEATHER_LABEL[previewWx ?? w?.condition ?? ''] ?? ''
  const t = w?.temperature != null ? `${Math.round(w.temperature)}${(w.unit || '°').replace(/[^°]/g, '') || '°'}` : ''
  return [t, label].filter(Boolean).join(' · ')
}
async function loadRules() { try { store.rules = await getScenes() } catch {} }
async function loadAmbient() {
  try { store.ambient = await getAmbient(); store.ambientLoaded = true } catch {}
  updateSky()
}

const ACTIVE = new Set(['on', 'playing', 'open', 'unlocked', 'cleaning', 'streaming', 'recording'])
export const isActive = (d: Device) => ACTIVE.has(d.state)
export const isDead = (d: Device) => d.state === 'unavailable' || d.state === 'unknown'
export const cap = (d: Device) => d.capability.split('.')[0]
export const PASSIVE = new Set(['sensor', 'motion', 'contact', 'camera'])
export const visibleRooms = () => {
  const rs = store.rooms.filter(r => r.id !== 'unassigned' || r.devices.length)
  return [...rs.filter(r => r.devices.length), ...rs.filter(r => !r.devices.length)]   // rooms with something in them first
}
export const roomOf = (d: Device) => store.rooms.find(r => r.id === d.room_id)
export const deviceById = (id: string) => { for (const r of store.rooms) { const d = r.devices.find(x => x.id === id); if (d) return d } }

/* ---------- names: say "Speaker" inside the Bedroom, not "Bedroom speaker" ---------- */
const GENERIC = /^((ceiling|floor|desk|table|main|left|right|wall|bedside|overhead|front|back|side) )?(speaker|tv|television|light|lights|lamp|fan|lock|door|blind|blinds|shade|shades|camera|plug|switch|thermostat|vacuum|window|motion|sensor|strip|doorbell)$/i
const norm = (s: string) => s.replace(/[’‘]/g, "'").toLowerCase().trim()
export function shortName(d: Device, room?: Room | null): string {
  let n = d.name.trim()
  if (room) {
    const r = norm(room.name), nn = norm(n)
    if (nn.startsWith(r + ' ')) {
      const rest = n.slice(r.length + 1).trim()
      if (rest && GENERIC.test(rest)) n = rest   // "Bedroom TV" → "TV"; "Garage View" (a camera's own name) stays whole
    }
  }
  return n.charAt(0).toUpperCase() + n.slice(1)
}

/* ---------- one line about a room, written for a person ---------- */
export function activity(r: Room): string {
  const parts: string[] = []
  const lights = r.devices.filter(d => cap(d) === 'light' && d.state === 'on').length
  if (lights) parts.push(lights === 1 ? '1 light on' : `${lights} lights on`)
  for (const d of r.devices.filter(d => cap(d) === 'media' && d.state === 'playing'))
    parts.push(d.attrs.media_title ? `${d.attrs.media_title}` : `${shortName(d, r)} playing`)
  const open = r.devices.filter(d => cap(d) === 'cover' && d.state === 'open').length
  if (open) parts.push(open === 1 ? 'Blind open' : `${open} blinds open`)
  if (r.devices.some(d => cap(d) === 'lock' && d.state === 'unlocked')) parts.push('Unlocked')
  if (r.devices.some(d => cap(d) === 'motion' && d.state === 'on')) parts.push('Motion')
  if (r.devices.some(d => cap(d) === 'camera' && d.state === 'recording')) parts.push('Recording')
  if (parts.length) return parts.join(' · ')
  if (!r.devices.length) return 'Nothing here yet'
  if (r.devices.every(d => cap(d) === 'camera')) return r.devices.length === 1 ? '1 camera' : `${r.devices.length} cameras`
  return 'Quiet'
}
export function roomActive(r: Room) { return r.devices.some(d => isActive(d) && cap(d) !== 'camera') }
/** Everything that is on across the house, cameras excluded: the "on right now" strip. */
export function whatsOn(): Device[] {
  return store.rooms.flatMap(r => r.devices.filter(d => isActive(d) && !PASSIVE.has(cap(d))))
}
export function houseLine(): string {
  if (!store.loaded) return store.error || 'Finding the house…'
  const on = whatsOn()
  if (!on.length) return `${store.homeName || 'The house'} is quiet.`
  const rooms = new Set(on.map(d => d.room_id))
  if (rooms.size === 1) return `Something is on in the ${roomOf(on[0])?.name ?? 'house'}.`
  return `Something is on in ${rooms.size} rooms.`
}

/* ---------- scenes: every button says what it will do ---------- */
export type Scene = { id: string; label: string; icon: string; needs: string[]; hint: (caps: Set<string>) => string }
const join = (xs: string[]) => xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]
const offList = (caps: Set<string>, extra = false) => join([
  caps.has('light') ? 'lights' : '', caps.has('media') ? 'screens' : '', extra && caps.has('switch') ? 'plugs' : '',
].filter(Boolean))
export const SCENES: Scene[] = [
  { id: 'movie', label: 'Movie', icon: 'film', needs: ['media'], hint: c => c.has('light') ? 'Lights low, screen on' : 'Screen on' },
  { id: 'guests', label: 'Guests', icon: 'sparkle', needs: ['light'], hint: () => 'Lights up bright' },
  { id: 'asleep', label: 'Sleep', icon: 'moon', needs: ['light', 'media', 'lock'], hint: c => `${cap1(offList(c))} off${c.has('lock') ? ', door locked' : ''}` },
  { id: 'empty', label: 'All off', icon: 'power', needs: ['light', 'media', 'switch', 'fan'], hint: c => cap1(join([c.has('light') ? 'lights off' : '', c.has('media') ? 'media paused' : ''].filter(Boolean))) },
]
export const HOUSE_SCENES: Scene[] = [
  { id: 'asleep', label: 'Bedtime', icon: 'moon', needs: [], hint: c => `${cap1(offList(c) || 'everything')} off in every room${c.has('lock') ? ', doors locked' : ''}` },
  { id: 'away', label: 'Everything off', icon: 'leave', needs: [], hint: c => `${cap1(offList(c, true) || 'everything')} off${c.has('lock') ? ', doors locked' : ''}` },
]
const cap1 = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
export const capsOf = (devices: Device[]) => new Set(devices.map(cap))
export function scenesFor(room: Room | null): Scene[] {
  if (!room) return store.rooms.some(r => r.devices.some(d => !PASSIVE.has(cap(d)))) ? HOUSE_SCENES : []
  const caps = capsOf(room.devices)
  return SCENES.filter(s => s.needs.some(c => caps.has(c)))
}
/* a scene 'holds' while every device it touches is still where the scene left it */
const EXPECT: Record<string, string[]> = { on: ['on', 'playing', 'paused', 'idle', 'buffering'], off: ['off', 'standby'], pause: ['paused', 'off', 'idle', 'standby'],
  play: ['playing'], lock: ['locked'], unlock: ['unlocked'], open: ['open', 'opening'], close: ['closed', 'closing'] }
export function sceneHolds(room: Room, id: string): boolean {
  const acts = store.rules[id]
  if (!acts || !acts.length) return false
  let touched = 0
  for (const [c, a] of acts) {
    const want = EXPECT[a]; if (!want) continue
    for (const d of room.devices) {
      if (cap(d) !== c || isDead(d)) continue
      touched++
      if (!want.includes(d.state)) return false
    }
  }
  return touched > 0
}
export function currentScene(room: Room): string | null {
  return room.intent && sceneHolds(room, room.intent) ? room.intent : null
}
export async function runScene(room: Room | null, scene: Scene): Promise<boolean> {
  try {
    if (room) { await setIntent(room.id, scene.id); room.intent = scene.id; notify(`${room.name} · ${scene.label}`) }
    else { await setHomeIntent(scene.id); for (const r of store.rooms) if (r.devices.length) r.intent = scene.id; notify(scene.id === 'asleep' ? 'Good night. The house is off.' : 'Everything is off.') }
    return true
  } catch (e: any) { notify(`That didn't work: ${e.message}`, 'error'); return false }
}

/* ---------- actions with instant feedback ---------- */
let toastId = 0, toastTimer: number | undefined
export function notify(text: string, kind: 'info' | 'error' = 'info') {
  store.toast = { id: ++toastId, text, kind }
  clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => (store.toast = null), kind === 'error' ? 5000 : 2800)
}
/** Apply the expected result right away, ask the house, and step back if it refuses. */
export async function perform(d: Device, action: string, data?: Record<string, unknown>, guess?: { state?: string; attrs?: Record<string, any> }) {
  const before = { state: d.state, attrs: { ...d.attrs } }
  if (guess?.state) d.state = guess.state
  if (guess?.attrs) d.attrs = { ...d.attrs, ...guess.attrs }
  store.pending[d.id] = true
  try { await act(d.id, action, data) }
  catch (e: any) {
    d.state = before.state; d.attrs = before.attrs; delete store.pending[d.id]
    notify(`${shortName(d, roomOf(d))} didn't respond`, 'error'); return false
  }
  window.setTimeout(() => delete store.pending[d.id], 5000)   // the stream normally clears it much sooner
  return true
}

/* ---------- recent activity, told plainly ---------- */
const LABELS: Record<string, string> = { movie: 'Movie', guests: 'Guests', asleep: 'Sleep', empty: 'All off', away: 'Everything off', occupied: 'Here' }
export function describe(ev: Event): { text: string; icon: string } | null {
  if (ev.kind === 'intent') {
    if (ev.subject === 'home') return { text: ev.new === 'asleep' ? 'Bedtime' : LABELS[ev.new ?? ''] ?? ev.new ?? '', icon: ev.new === 'asleep' ? 'moon' : 'leave' }
    const r = store.rooms.find(r => r.id === ev.subject)
    return r ? { text: `${r.name} set to ${LABELS[ev.new ?? ''] ?? ev.new}`, icon: 'sparkle' } : null
  }
  if (ev.kind !== 'state' || ev.old === ev.new) return null
  const d = deviceById(ev.subject); if (!d) return null
  const n = d.name, k = cap(d), s = ev.new ?? ''
  if (s === 'unavailable') return { text: `${n} went offline`, icon: k }
  if (ev.old === 'unavailable') return { text: `${n} is back`, icon: k }
  let detail: any = null; try { detail = ev.detail ? JSON.parse(ev.detail) : null } catch {}
  if (k === 'light' || k === 'switch' || k === 'fan') return s === 'on' || s === 'off' ? { text: `${n} turned ${s}`, icon: k } : null
  if (k === 'media') {
    if (s === 'playing') return { text: detail?.media_title ? `${n} started playing ${detail.media_title}` : `${n} started playing`, icon: k }
    if (s === 'paused') return { text: `${n} paused`, icon: k }
    if (s === 'off') return { text: `${n} turned off`, icon: k }
    return null
  }
  if (k === 'camera') return s === 'recording' ? { text: `${n} started recording`, icon: k } : null
  if (k === 'motion') return s === 'on' ? { text: `Motion at ${n}`, icon: k } : null
  if (k === 'contact') return s === 'on' ? { text: `${n} opened`, icon: k } : s === 'off' ? { text: `${n} closed`, icon: k } : null
  if (k === 'lock') return s === 'locked' || s === 'unlocked' ? { text: `${n} ${s}`, icon: k } : null
  if (k === 'cover') return s === 'open' || s === 'closed' ? { text: `${n} ${s === 'open' ? 'opened' : 'closed'}`, icon: k } : null
  return null
}
export function ago(ts: number, now = Date.now()): string {
  const s = Math.max(0, (now - ts * 1000) / 1000)
  if (s < 60) return 'Just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts * 1000).toLocaleDateString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}
let eventsTimer: number | undefined
export async function refreshEvents() {
  try { store.events = await getEvents(60) } catch {}
}
function eventsSoon() { clearTimeout(eventsTimer); eventsTimer = window.setTimeout(refreshEvents, 1500) }

/* ---------- setup and things found nearby ---------- */
/** True while the panel should show the setup flow instead of the house. */
export const needsSetup = () => !store.status || store.status.driver !== 'ready' || !store.status.setup_done
export async function refreshStatus() {
  try { store.status = await getStatus() } catch { if (!store.status) store.error = 'The hub is not answering.' }
}
let foundTimer: number | undefined
export async function refreshFound() {
  if (store.status?.driver !== 'ready') return
  try { store.found = await getDiscovered() } catch {}
}
function foundSoon() { clearTimeout(foundTimer); foundTimer = window.setTimeout(refreshFound, 2500) }

/* ---------- lifecycle ---------- */
function applyHome(h: Home) { store.rooms = h.rooms; store.homeName = h.name || ''; store.loaded = true; store.error = ''; foundSoon(); if (store.homeName) document.title = store.homeName }
/** A room was set to a state by a rule or by another screen: keep the chip honest without a reload. */
function applyIntent(i: Intent) {
  const r = store.rooms.find(r => r.id === i.room)
  if (r) { r.intent = i.intent; r.set_by = i.set_by; r.hold_until = i.hold_until; eventsSoon() }
}
function applyDevice(d: Device) {
  for (const r of store.rooms) {
    const i = r.devices.findIndex(x => x.id === d.id)
    if (i >= 0) { r.devices[i] = d; delete store.pending[d.id]; if (store.viewer?.id === d.id) store.viewer = d; eventsSoon(); return }
  }
}
let stop: (() => void) | undefined, lostTimer: number | undefined, skyTimer: number | undefined
export async function load() {
  await refreshStatus()
  try { applyHome(await getHome()) } catch { store.error = 'The hub is not answering.' }
  loadAmbient(); loadRules()
}
let foundPoll: number | undefined
export async function start() {
  await load()
  updateSky(); clearInterval(skyTimer); skyTimer = window.setInterval(updateSky, 30000)
  clearInterval(foundPoll); foundPoll = window.setInterval(refreshFound, 60000)
  stop = connect({ device: applyDevice, home: applyHome, intent: applyIntent, ambient: a => { store.ambient = a; updateSky() }, status: s => {
    const was = store.status?.driver
    store.status = s
    if (s.driver === 'ready' && was !== 'ready') { load() }   // the engine just came up: read the house
  }, link: v => {
    store.linkUp = v
    clearTimeout(lostTimer)
    if (v) { store.linkLost = false; if (!store.loaded) load() }
    else lostTimer = window.setTimeout(() => (store.linkLost = true), 4000)   // a blink on startup is not worth a banner
  } })
}
export function halt() { stop?.(); clearInterval(skyTimer); clearInterval(foundPoll) }
