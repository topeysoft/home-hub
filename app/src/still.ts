// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The freshest picture we have of a camera, and when it was actually taken.
 *
 * Every camera surface used to do this for itself: point an <img> at the still route with a
 * cache-buster, and date the picture from the moment the <img> fired load. That reads as freshness
 * and is not. HA hands back whatever the integration is holding, and a cloud camera holds one frame
 * for hours -- Ring cuts its still out of the last recorded video -- so a dark 4am frame arrived
 * every fifteen seconds wearing a "Just now" chip, on a bright afternoon.
 *
 * So the still is fetched rather than assigned: the brain dates the bytes (X-Frame-Age) and the age
 * on the chip is the frame's, not the fetch's. Three things follow from owning the fetch:
 *
 *   - a frame that has not changed is not asked for again as eagerly. The poll backs off to a
 *     couple of minutes while nothing moves and drops to BASE the moment it does. A house of Ring
 *     cameras was spending a cloud call every fifteen seconds per camera to be handed the same JPEG.
 *   - one camera is fetched once however many cards are showing it. The Rooms tab, a room's tiles
 *     and the pane behind them share a watch and a picture.
 *   - the viewer can put a live frame in here (`fromLive`). WebRTC is the only genuinely current
 *     picture a cloud camera has, so a glance at the doorbell leaves today's daylight on the card
 *     instead of last night -- and it ages honestly from the second it was grabbed.
 */
import { computed, onUnmounted, reactive, ref, watch } from 'vue'

export type Still = {
  url: string          // an object URL for the frame, '' until one arrives
  at: number           // when the picture was taken, as near as anyone can say
  live: boolean        // grabbed off the moving picture rather than the still route
  failed: boolean      // the last fetch did not come back with a picture
}

const stills = reactive<Record<string, Still>>({})
export const BASE = 15000            // how often a camera is asked while its picture keeps changing
export const SLOWEST = 120000        // and the longest we wait while it does not
const LIVE_WIDTH = 640               // a card is never bigger than this; a full frame would cost memory for nothing

type Watch = { users: number; every: number; base: number; tag: string; timer?: number; stopped?: boolean }
const watches: Record<string, Watch> = {}

/** One clock for every chip on screen, rather than one interval per card. */
const clock = ref(Date.now())
let ticking: number | undefined
function tick(on: boolean) {
  if (on && ticking === undefined) { clock.value = Date.now(); ticking = window.setInterval(() => (clock.value = Date.now()), 1000) }
  else if (!on && !Object.keys(watches).length) { clearInterval(ticking); ticking = undefined }
}
/** How old a picture is, in the words a chip has room for. Reads the shared clock, so a chip
    written with it re-renders every second without the surface owning a timer. */
export function ageLabel(at: number, asOf = clock.value): string {
  const s = Math.max(0, Math.round((asOf - at) / 1000))
  if (s < 5) return 'Just now'
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`
}

function keep(id: string, next: Still) {
  const was = stills[id]
  if (was?.url && was.url !== next.url) URL.revokeObjectURL(was.url)
  stills[id] = next
}

function schedule(id: string, ms: number) {
  const w = watches[id]
  if (!w || w.stopped) return
  w.timer = window.setTimeout(() => void poll(id), ms)
}

async function poll(id: string) {
  const w = watches[id]
  if (!w || w.stopped) return
  // A hidden panel is a resting panel: nothing is being looked at, and a camera should not be woken for it.
  if (document.hidden) return schedule(id, w.every)
  try {
    const r = await fetch(`/devices/${encodeURIComponent(id)}/image`, {
      cache: 'no-store',
      headers: w.tag ? { 'If-None-Match': `"${w.tag}"` } : {},
    })
    if (r.status === 304) { w.every = Math.min(w.every * 2, SLOWEST); if (stills[id]) stills[id].failed = false }
    else if (r.ok) {
      const tag = (r.headers.get('ETag') || '').replace(/^W\//, '').replace(/"/g, '')
      const at = Date.now() - Number(r.headers.get('X-Frame-Age') || 0) * 1000
      const blob = await r.blob()
      if (!blob.size) throw new Error('no bytes')
      const same = !!tag && tag === w.tag
      w.tag = tag || w.tag
      w.every = same ? Math.min(w.every * 2, SLOWEST) : w.base
      const showing = stills[id]
      // The viewer's frame beats the brain's whenever it is the newer of the two: a still route that
      // is still handing out last night must not paint over the daylight we just watched.
      if (same || (showing?.live && showing.at >= at)) { if (showing) showing.failed = false }
      else keep(id, { url: URL.createObjectURL(blob), at, live: false, failed: false })
    } else throw new Error(String(r.status))
  } catch {
    // Keep the last picture up -- a camera that misses one poll has not stopped being a camera -- but
    // say so, so a surface that has never had a frame can draw something else.
    if (stills[id]) stills[id].failed = true
    else stills[id] = { url: '', at: 0, live: false, failed: true }
    w.every = Math.min(w.every * 2, SLOWEST)
  }
  schedule(id, w.every)
}

/** The frame we are holding for a camera, whether or not anything is watching it. */
export function stillFor(id: string | undefined): Still {
  return (id && stills[id]) || { url: '', at: 0, live: false, failed: false }
}

/** Watch one camera. Returns the release: the fetching stops when the last watcher lets go. */
export function watchStill(id: string, base = BASE): () => void {
  const w = watches[id] ?? (watches[id] = { users: 0, every: base, base, tag: '' })
  w.base = Math.min(w.base, base)          // the most eager surface on screen sets the pace for the rest
  w.users++
  tick(true)
  if (w.users === 1) { w.stopped = false; void poll(id) }
  let held = true
  return () => {
    if (!held) return
    held = false
    if (--w.users > 0) return
    w.stopped = true
    clearTimeout(w.timer)
    delete watches[id]
    tick(false)
    // The frame itself stays: coming back to a tab should show the last picture at once, with its
    // age still telling the truth about how old it is.
  }
}

/**
 * The still for a camera, watched while the component is alive. `id` may go undefined -- an offline
 * camera, a viewer with nothing open -- and the watching stops for as long as it is.
 */
export function useStill(id: () => string | undefined, base = BASE) {
  let release: (() => void) | undefined
  watch(id, (next) => {
    release?.(); release = undefined
    if (next) release = watchStill(next, base)
  }, { immediate: true })
  onUnmounted(() => release?.())
  return computed<Still>(() => stillFor(id()))
}

/**
 * A frame off the moving picture. For a camera whose still route only ever returns the last recorded
 * event, this is the one current picture of the house there is, so the viewer hands one over while it
 * plays and every card showing that camera gets it.
 */
export function fromLive(id: string, video: HTMLVideoElement) {
  const w = video.videoWidth, h = video.videoHeight
  if (!w || !h) return
  const scale = Math.min(1, LIVE_WIDTH / w)
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale)
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  canvas.toBlob(b => { if (b) keep(id, { url: URL.createObjectURL(b), at: Date.now(), live: true, failed: false }) }, 'image/jpeg', 0.8)
}

/** For tests: forget every frame and every watch. */
export function forget() {
  for (const id of Object.keys(watches)) { watches[id].stopped = true; clearTimeout(watches[id].timer); delete watches[id] }
  for (const id of Object.keys(stills)) { if (stills[id].url) URL.revokeObjectURL(stills[id].url); delete stills[id] }
  clearInterval(ticking); ticking = undefined
}
