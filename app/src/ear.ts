// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Where a spoken sentence comes from -- and nothing whatever about what it means.
 *
 * `docs/voice.md` settled on 14 September 2026 that the wall's words are recognised on the hub
 * (shape 2) and that a phone browser's own recogniser is shape 1, behind the certificate in
 * `docs/away.md`. Neither exists yet, so `canListen()` is false in every house and the orb keeps
 * the only job it has ever had: a tap opens the box to type in. That is the degradation the gesture
 * was chosen for -- there is no control to hide, and no second path through `Say.vue` for the
 * panels that cannot listen.
 *
 * What this file is for today is the SHAPE, so move 6 can be drawn against something. Two sources
 * will sit behind it when they exist, and neither of them draws anything: `getUserMedia` in a
 * browser that has it, and the kiosk's bridge on the wall, where a WebView has no secure context to
 * ask from. The panel asks for a sentence back; it never asks who heard it.
 */

/** What the panel wants back. `heard` is a whole sentence; `ended` is listening stopping without one;
 *  `failed` is the house having to say why it cannot listen, in words a person can act on. */
export type Listener = {
  heard(said: string): void
  ended(): void
  failed(why: string): void
  /** the sentence so far, while it is still being said. Optional: the stub has nothing to offer. */
  hearing?(sofar: string): void
}

/** A turn of listening, from the tap that started it. */
export type Ear = { stop(): void }

/* The preview, and the only source there is. `?listen=1` gives the orb something to be listening to
   so the move can be looked at and tested before any engine exists -- the same kind of preview flag
   the panel already carries for the resting screen (`?rest=1`) and the join screen (`?join=1`).

   It hears nothing on its own. A sentence arrives when the page is handed one, through `__hear` on
   the window, which is what makes the ring's single shot something a test can time rather than a
   race with a timer. Nothing outside a preview ever defines it. */
const mode = () => new URLSearchParams(location.search).get('listen')
const previewing = () => mode() === '1'
/* `browser` asks for on-device and falls back to whatever the browser does; `browser-local` refuses
   the fallback. Both are the same engine, so both come through here. */
const browserMode = () => mode() === 'browser' || mode() === 'browser-local'

/** Whether anything in this panel can listen at all. False in every house today. */
export function canListen(): boolean {
  return previewing() || (browserMode() && !!recogniser.Ctor)
}

/** Start a turn of listening, or answer null where nothing can hear. */
export function listen(to: Listener): Ear | null {
  if (browserMode()) return browserEar(to)
  if (!previewing()) return null
  const w = window as unknown as Record<string, unknown>
  let live = true
  const shut = () => {
    if (!live) return false
    live = false
    delete w.__hear
    delete w.__ended
    return true
  }
  w.__hear = (said: unknown) => { if (shut()) to.heard(String(said)) }
  w.__ended = () => { if (shut()) to.ended() }
  /* The person tapped again. `ended` is not called for that: they know they stopped, and the orb
     has already been told to come down by the hand that did it. */
  return { stop() { shut() } }
}

/* ---------- a browser's own recogniser, for looking at this on your own machine ----------
 *
 * `?listen=browser`, and never without it. This is shape 1's engine and `docs/voice.md` has not let
 * it ship: Chrome's `SpeechRecognition` has historically sent the audio away to Google to be
 * recognised, and a panel that did that by default would break *works with the internet down* and
 * *no vendor account* in one move. So it stays behind a flag, `canListen()` is still false in every
 * house, and what this is for is the two things the plan actually asks for -- somewhere to watch
 * move 6 with a real voice, and somewhere to answer *whether the browser's recognition really runs
 * on the device*, which is still an open decision in that file.
 *
 * It needs no certificate on your own machine: `http://localhost` is a secure context already, and
 * so is `127.0.0.1`. A phone pointed at this Mac over the LAN is not one, and that is the only case
 * a local certificate is for.
 */
const recogniser = {
  get Ctor() {
    const w = window as unknown as Record<string, unknown>
    return (w.SpeechRecognition ?? w.webkitSpeechRecognition) as (new () => SpeechLike) | undefined
  },
}

/** Only the handful of this API the panel touches; the rest of it is not our business. */
type SpeechLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  processLocally?: boolean
  start(): void
  stop(): void
  abort(): void
  onresult: ((e: SpeechEvent) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}

/** Results pile up across an utterance, so the whole list is read each time rather than the newest. */
type SpeechEvent = {
  results: { length: number; [i: number]: { isFinal: boolean; 0: { transcript: string } } }
}

/* How long the house waits before deciding you have stopped talking.
 *
 * This is the endpointer docs/voice.md says is the substance of shape 1 -- "cut off mid-sentence if
 * it is impatient, left hanging if it is not" -- and it has to be OURS. Chrome's own is impatient:
 * with `continuous` off it ends the turn at the first pause, so "set thermostat to seventy two"
 * comes back as "set". With it on, Chrome never decides at all, and this timer does. A second and a
 * half is long enough to think mid-sentence and short enough not to feel ignored. */
const PATIENCE = 1500

/* And how long it waits for you to START, which is a different question and a much longer answer.
   A tap is not a promise to speak immediately: somebody crosses the room, or thinks. Ending the turn
   1.5s after a tap because nobody had said anything yet is the same impatience, one step earlier. */
const OPENING = 6000

/* What a browser says when it cannot listen, said the way the panel says everything else: what
   happened, and what the person can do about it. `network` is the one worth reading twice -- it
   means the recogniser went looking for a cloud, which is the thing this plan will not ship. */
const WHY: Record<string, string> = {
  'not-allowed': 'This browser is not letting the panel hear. Allow the microphone and try again.',
  'service-not-allowed': 'This browser is not letting the panel hear. Allow the microphone and try again.',
  'audio-capture': 'No microphone on this machine.',
  'no-speech': "Didn't catch that.",
  network: 'That browser sends speech away to be recognised, and it could not reach the service.',
  aborted: '',
  'language-not-supported':
    'This browser has no on-device model for this language, and was told not to use a cloud.',
}

/* The one error worth a second go. Chrome answers it when `processLocally` was asked for and the
   model has not been fetched, which on a machine that has never used this API is every time. */
const NO_MODEL = 'language-not-supported'

function browserEar(to: Listener): Ear | null {
  const Ctor = recogniser.Ctor
  if (!Ctor) return null
  /* `?listen=browser-local` refuses the cloud outright. That is the strict half of the measurement
     docs/voice.md is waiting on: if this starts and hears you, on-device recognition is really
     there; if it will not start, it is not, and shape 1 cannot honour *works with the internet
     down* on this browser however well it performs. Plain `?listen=browser` asks for on-device
     first and falls back once, loudly, so the move can still be looked at on any machine. */
  const strict = mode() === 'browser-local'
  let live = true
  let rec: SpeechLike | null = null
  const shut = () => {
    if (!live) return false
    live = false
    return true
  }

  /* What has been heard so far, and the timer that decides the sentence is over. Both live out here
     rather than inside `attach`, so a fallback to the cloud keeps the words already spoken. */
  let sofar = ''
  let patience: ReturnType<typeof setTimeout> | undefined
  const rest = () => {
    clearTimeout(patience)
    patience = undefined
  }

  const attach = (local: boolean): boolean => {
    const r = new Ctor()
    r.lang = navigator.language || 'en-GB'
    /* `continuous` is what stops Chrome ending the turn at the first breath, and `interimResults` is
       what keeps words arriving while somebody is still talking -- both are what the timer below
       needs to know they have not finished. */
    r.continuous = true
    r.interimResults = true
    r.maxAlternatives = 1
    const offered = 'processLocally' in r
    if (local && offered) r.processLocally = true

    /* The sentence is over when the house says so. `stop()` rather than `abort()`, so whatever was
       being recognised at the moment of silence still arrives. */
    const done = () => {
      rest()
      const said = sofar.trim()
      if (!shut()) return
      r.stop()
      said ? to.heard(said) : to.ended()
    }
    const waitAgain = () => {
      rest()
      patience = setTimeout(done, sofar ? PATIENCE : OPENING)
    }

    r.onresult = (e) => {
      let whole = ''
      for (let k = 0; k < e.results.length; k++) whole += e.results[k][0].transcript
      sofar = whole
      to.hearing?.(whole.trim())
      /* every new word buys another PATIENCE: the pause that ends a sentence is silence, not a comma */
      waitAgain()
    }
    r.onerror = (e) => {
      /* the model is missing, not the microphone: drop to whatever the browser does by default and
         say so, because what it does by default is very probably send the audio away */
      if (local && !strict && e.error === NO_MODEL) {
        console.warn('[ear] no on-device model here; falling back -- THE AUDIO IS LEAVING THIS MACHINE')
        if (attach(false)) return
      }
      /* Chrome says `no-speech` at its own pace; while the house is still waiting that is not an
         answer, it is just quiet. Our own timer is the one that gets to end this. */
      if (e.error === 'no-speech' && patience) return
      rest()
      if (!shut()) return
      const why = WHY[e.error] ?? `The microphone stopped: ${e.error}.`
      console.warn(`[ear] ${e.error}`)
      why ? to.failed(why) : to.ended()
    }
    r.onend = () => {
      /* Chrome gave up before we did -- take what there is rather than throwing the sentence away */
      if (rec !== r) return
      rest()
      const said = sofar.trim()
      if (shut()) said ? to.heard(said) : to.ended()
    }
    try {
      r.start()
    } catch (err) {
      /* start() throws where the API is there but the browser will not use it -- an insecure origin
         is the usual one, which is a phone pointed at this machine over the LAN rather than at
         localhost */
      if (shut()) to.failed(`This browser would not start listening: ${(err as Error).message}`)
      return false
    }
    /* warn and not info: a browser that does not offer on-device recognition is very likely sending
       a voice somewhere, and that is worth saying out loud every single time it happens */
    console.warn(
      `[ear] ${r.lang}; on-device ${!local ? 'refused -- audio is leaving this machine' : offered ? 'asked for' : 'NOT offered by this browser'}`,
    )
    rec = r
    waitAgain()
    return true
  }

  if (!attach(true)) return null
  return {
    stop() {
      rest()
      if (shut()) rec?.abort()
    },
  }
}
