// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * Which door this page reaches the hub through (design/away/, C; docs/away.md).
 *
 * A phone that has moved to the house's own name -- https://maple-court.elyir.app -- loads the app there,
 * from wherever it is. On the sofa, going out to the relay and back for every tap is exactly what the
 * relay is not for, so the app looks for the hub's name at home -- https://192-168-86-53.maple-court.home.elyir.app,
 * which the relay's DNS answers with the hub's LAN address -- and talks to it directly when it answers.
 * Away, that name is a private address nobody can reach, the look fails fast, and everything goes the
 * way the page came: through the relay.
 *
 * Two names are two origins, and a browser keeps a cookie per name, so the phone carries its token itself
 * here -- in this origin's storage, sent as `Authorization: Bearer` and, on a websocket, as a subprotocol so
 * it is never in a URL. A page on hub.local never has a token and never looks: it is already at home.
 */
import { reactive } from 'vue'

const TOKEN = 'hub-token', LAN = 'hub-lan'
const read = (k: string) => { try { return localStorage.getItem(k) || '' } catch { return '' } }
const write = (k: string, v: string) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k) } catch { /* a private window keeps nothing */ } }

export const door = reactive({
  token: read(TOKEN),     // this phone's token on this origin, set by the move (empty on hub.local)
  lan: read(LAN),         // the hub's name at home, as the hub last said it
  base: '',               // '' for this page's own origin, or https://<lan> while it answers
})

/** The move landed: this origin's token, and the name at home to look for. */
export function moved(token: string, lan: string | null) {
  door.token = token; write(TOKEN, token)
  learnLan(lan)
}

/** Inside the Houses app (inapp.ts): the pass the app handed over, kept in memory only -- the app keeps it. */
export function carry(token: string, lan: string | null) {
  door.token = token
  door.lan = lan && /^[a-z0-9.-]+\.home\.[a-z0-9.-]+$/.test(lan) ? lan : ''
}

export function learnLan(lan: string | null | undefined) {
  const v = lan && /^[a-z0-9.-]+\.home\.[a-z0-9.-]+$/.test(lan) ? lan : ''
  if (v === door.lan) return
  door.lan = v; write(LAN, v)
  if (!v) door.base = ''
}

/** Only a moved phone on the house's own name looks for the hub at home; hub.local is already there. */
export const looks = () => !!door.token && !!door.lan && location.protocol === 'https:' && location.hostname !== door.lan

let looking: Promise<void> | null = null
/** Is the hub's name at home answering? A second and a half, then the relay. */
export function look(): Promise<void> {
  if (!looks()) { door.base = ''; return Promise.resolve() }
  looking ??= (async () => {
    const at = `https://${door.lan}`
    try {
      const r = await fetch(`${at}/alive`, { signal: AbortSignal.timeout(1500), cache: 'no-store' })
      door.base = r.ok ? at : ''
    } catch { door.base = '' }
  })().finally(() => { looking = null })
  return looking
}

export const apiUrl = (path: string) => (door.base && path.startsWith('/') ? door.base + path : path)

export function wsUrl(path: string) {
  if (door.base) return door.base.replace(/^https:/, 'wss:') + path
  return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${path}`
}

/** The token as a websocket subprotocol pair, `hub, <token>`, or nothing on hub.local, where the cookie does it. */
export const wsProtocols = (): string[] | undefined => (door.token ? ['hub', door.token] : undefined)

export function withToken(headers: Headers) {
  if (door.token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${door.token}`)
  return headers
}

/** Looking again when it could have changed: the phone came back to the page, or the link dropped. */
export function watchDoor(onChange: () => void) {
  let was = door.base
  const again = () => look().then(() => { if (door.base !== was) { was = door.base; onChange() } })
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') again() })
  window.addEventListener('online', again)
  return again
}
