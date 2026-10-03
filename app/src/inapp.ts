// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The panel inside the Houses app (design/houses/, B and The app, decided 2 and 3 October).
 *
 * A phone keeps every house it has joined in one app at houses.elyir.app, and each house's own panel is
 * framed inside it, loaded from that house's own name. The app holds the house's pass; the panel asks for
 * it once it has loaded and keeps it in memory only, because the app is where the phone keeps it -- on an
 * iPhone, the Home Screen app's storage is its own, and this frame's is somewhere else again.
 *
 * Both sides check who they are talking to. The panel takes a pass only from its parent, and only when the
 * parent is the app. The app hands a pass only to the house it loaded, at that house's origin (the app's
 * own side of this). Nothing secret ever goes out of here: the panel's own messages say it is ready, whether
 * it is connected, and that somebody tapped the house's name.
 */
import { reactive } from 'vue'
import { carry } from './door'

/** The app, and its dev server on its developer's own machine. */
export const APP_ORIGINS = ['https://houses.elyir.app', 'http://localhost:5174']

/** Framed by the app: it loads each house with ?app=1. */
export const inApp = (() => {
  try { return window.parent !== window && new URLSearchParams(location.search).has('app') } catch { return false }
})()

/** What the app says about the houses: this one's name on this phone, and whether another house wants somebody. */
export const app = reactive({ name: '', others: false })

let appOrigin = ''

function house(m: any) {
  if (typeof m?.name === 'string') app.name = m.name.slice(0, 40)
  app.others = !!m?.others
}

/** Wait for the app to hand over the house's pass. Says it is ready every half second, for eight seconds;
    after that the panel goes on without one, and the house shows the way in, as it would to anybody. */
export function carried(): Promise<void> {
  if (!inApp) return Promise.resolve()
  return new Promise(resolve => {
    const ready = () => window.parent.postMessage({ type: 'houses:ready' }, '*')
    const every = window.setInterval(ready, 500)
    const giveUp = window.setTimeout(() => { window.clearInterval(every); resolve() }, 8000)
    window.addEventListener('message', ev => {
      if (ev.source !== window.parent || !APP_ORIGINS.includes(ev.origin)) return
      const m = ev.data
      if (m?.type === 'houses:token' && typeof m.token === 'string' && m.token) {
        appOrigin = ev.origin
        carry(m.token, typeof m.lan === 'string' ? m.lan : null)
        house(m)
        window.clearInterval(every); window.clearTimeout(giveUp); resolve()
      } else if (m?.type === 'houses:house') house(m)
    })
    ready()
  })
}

/** Tell the app something. Only once it has spoken, and only to it. */
export function tell(type: string, data: Record<string, unknown> = {}) {
  if (inApp && appOrigin) window.parent.postMessage({ type, ...data }, appOrigin)
}

/** Somebody tapped the house's name: the app opens Houses over it (HereB-sheet). */
export const openHouses = () => tell('houses:open')
