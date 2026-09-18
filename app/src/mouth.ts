// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Where a spoken answer comes out -- and nothing whatever about what it means.
 *
 * `ear.ts`'s opposite number, and deliberately the same shape: the panel asks for a sentence to be
 * said and never asks who says it. `docs/voice.md` settled on 14 September 2026 that the PANEL plays
 * the answer, as audio in the page, from a clip the hub synthesised and hosts on its own LAN address
 * -- the arrangement `sounds.py` already has with a Cast speaker, so *works with the internet down*
 * is inherited rather than argued for again. Not natively in the kiosk (`docs/apps.md`: nothing lives
 * only in the app, and the wall contributes a loudspeaker rather than a feature), and not on the
 * room's speaker, because an answer has to come from where the hand was.
 *
 * The kiosk is already ready for this and was before the plan was written:
 * `kiosk/app/src/main/java/app/elyir/kiosk/Wall.kt:201` sets `mediaPlaybackRequiresUserGesture = false`
 * with the comment *a sound a rule started just plays*. On a phone, the tap that started the sentence
 * is the gesture, so neither needs one.
 *
 * WHEN the house speaks is not decided here. The brain decides it -- the route rule and the sleeping
 * room, in `brain/hub/voice.py` -- and a reply either carries a clip or does not. This file plays what
 * it is handed.
 */
import type { Spoken } from './api'

/* Only one thing ever speaks. Within a panel that is this variable: a second answer stops the first
   rather than talking over it, which is the same rule the brain keeps between two panels in earshot. */
let mouth: HTMLAudioElement | null = null
let browser = false

const mode = () => new URLSearchParams(location.search).get('speak')

/** Stop whatever the house is in the middle of saying. */
export function hush() {
  if (mouth) { mouth.pause(); mouth.src = ''; mouth = null }
  if (browser) { browser = false; try { window.speechSynthesis?.cancel() } catch {} }
}

/** Say a reply out loud, if there is anything in it to say. True when something actually starts. */
export function speak(answer: { speak?: Spoken | null; spoken?: string | null } | null | undefined): boolean {
  hush()
  if (!answer) return false
  if (answer.speak?.url) return play(answer.speak.url)
  /* No clip. Either this hub has no voice -- which is every house today, and the answer is on the
     glass where it has always been -- or this is somebody looking at the answering half on their own
     machine before there is a container to look at it with. */
  if (preview() && answer.spoken) return say(answer.spoken)
  return false
}

function play(url: string): boolean {
  const a = new Audio(url)
  mouth = a
  a.addEventListener('ended', () => { if (mouth === a) mouth = null })
  /* A clip that will not play is not worth a word to anybody: the sentence is already on the screen,
     and a house that interrupts itself to apologise for its loudspeaker is worse than a quiet one. */
  a.play().catch((e) => { if (mouth === a) mouth = null; console.warn('[mouth] could not play the answer', e) })
  return true
}

/* ---------- the browser's own voice, for looking at this on your own machine ----------
 *
 * `?speak=browser`, and never without it -- exactly the shape `ear.ts` uses for `?listen=browser`,
 * and for the same reason. `speechSynthesis` is a vendor's voice on several platforms and a network
 * call on some of them, and a panel that used it by default would break *works with the internet
 * down* and *no vendor account* in one move. So it stays behind a flag and no house ever reaches it.
 *
 * What it is FOR is the thing the plan asks for: the answering half, and the rules around it, can be
 * seen and HEARD before Piper is running anywhere -- the same preview `?listen=1` gives the orb.
 */
const preview = () => mode() === 'browser'

function say(line: string): boolean {
  const synth = window.speechSynthesis
  if (!synth || typeof SpeechSynthesisUtterance === 'undefined') return false
  console.warn('[mouth] ?speak=browser: this is the BROWSER speaking, not the house')
  const u = new SpeechSynthesisUtterance(line)
  u.lang = navigator.language || 'en-GB'
  u.onend = () => { browser = false }
  browser = true
  synth.speak(u)
  return true
}
