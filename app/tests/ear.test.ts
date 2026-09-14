/* Where a spoken sentence comes from.

   Nothing in any house can listen yet -- docs/voice.md left the wall's words to the hub and a
   phone's to a certificate that does not exist -- so the first thing asserted here is the
   DEGRADATION, because it is the one every panel is running today: the orb answers no, and Say.vue
   falls back to the line it has always had. The rest holds the preview honest, since move 6 is
   drawn against it and a move drawn against a lie is drawn wrong. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { canListen, listen } from '../src/ear'

const at = (search: string) => vi.stubGlobal('location', { ...window.location, search })
const heard: string[] = []
const listener = {
  heard: (said: string) => heard.push(said),
  ended: () => heard.push('(ended)'),
  failed: (why: string) => heard.push(`(failed) ${why}`),
}
const hooks = () => window as unknown as { __hear?: (s: string) => void; __ended?: () => void }

afterEach(() => {
  heard.length = 0
  delete hooks().__hear
  delete hooks().__ended
  vi.unstubAllGlobals()
})

describe('a house with nothing to listen with, which is every house today', () => {
  it('says so, so the tap can stay the way into the box', () => {
    at('')
    expect(canListen()).toBe(false)
    expect(listen(listener)).toBeNull()
  })

  it('leaves no hook on the window for anything to find', () => {
    at('')
    listen(listener)
    expect(hooks().__hear).toBeUndefined()
  })
})

describe('the preview, which is what move 6 is drawn against', () => {
  it('hears a whole sentence, once', () => {
    at('?listen=1')
    expect(canListen()).toBe(true)
    const ear = listen(listener)!
    expect(ear).not.toBeNull()
    hooks().__hear!('kitchen lights off')
    expect(heard).toEqual(['kitchen lights off'])
  })

  it('is done after that sentence: a turn of listening is one sentence long', () => {
    at('?listen=1')
    listen(listener)
    hooks().__hear!('kitchen lights off')
    expect(hooks().__hear).toBeUndefined()
    expect(heard).toEqual(['kitchen lights off'])
  })

  it('ends without one when the endpointer gives up', () => {
    at('?listen=1')
    listen(listener)
    hooks().__ended!()
    expect(heard).toEqual(['(ended)'])
  })

  it('says nothing back when the person stops it themselves', () => {
    /* a second tap is the stop, and the hand that did it has already taken the orb down -- an
       `ended` on top of that would be the panel telling somebody what they just did */
    at('?listen=1')
    const ear = listen(listener)!
    ear.stop()
    expect(heard).toEqual([])
    expect(hooks().__hear).toBeUndefined()
  })

  it('cannot be stopped twice into an answer', () => {
    at('?listen=1')
    const ear = listen(listener)!
    ear.stop()
    ear.stop()
    expect(heard).toEqual([])
  })
})

/* The browser's own recogniser, which is shape 1's engine and is behind `?listen=browser` because
   docs/voice.md will not have it shipped: a browser that recognises in a cloud breaks *works with
   the internet down*. What is checked here is that it stays behind that flag, that it says WHY when
   it cannot listen rather than going quiet, and that a browser with no Web Speech API at all --
   which is the WebView on the wall, and the whole reason the wall's voice went to the hub -- is
   simply answered no. */
class FakeSpeech {
  static last: FakeSpeech | null = null
  lang = ''
  continuous = false
  interimResults = false
  maxAlternatives = 0
  started = false
  aborted = false
  stopped = false
  processLocally?: boolean
  onresult: ((e: unknown) => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  constructor() {
    FakeSpeech.last = this
  }
  start() {
    this.started = true
  }
  abort() {
    this.aborted = true
  }
  stop() {
    this.stopped = true
  }
}

/** Results pile up across an utterance, so a sentence is a LIST of them, not one. */
const said = (...parts: string[]) => ({
  results: Object.assign(
    parts.map((transcript) => ({ isFinal: true, 0: { transcript } })),
    { length: parts.length },
  ),
})

describe('a browser that can hear, behind the flag', () => {
  beforeEach(() => {
    FakeSpeech.last = null
    vi.useFakeTimers()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('SpeechRecognition', FakeSpeech)
  })
  afterEach(() => vi.useRealTimers())

  /** nobody has said anything for long enough that the house decides the sentence is over */
  const silence = () => vi.advanceTimersByTime(1600)

  it('stays behind the flag: a house without it is still a house that cannot listen', () => {
    at('')
    expect(canListen()).toBe(false)
    expect(listen(listener)).toBeNull()
  })

  it('starts listening, and hears a sentence', () => {
    at('?listen=browser')
    expect(canListen()).toBe(true)
    expect(listen(listener)).not.toBeNull()
    expect(FakeSpeech.last!.started).toBe(true)
    FakeSpeech.last!.onresult!(said('  kitchen lights off  '))
    expect(heard, 'it answered before the sentence was over').toEqual([])
    silence()
    expect(heard).toEqual(['kitchen lights off'])
    expect(FakeSpeech.last!.stopped, 'it was cut off rather than let finish').toBe(true)
  })

  it('does not end the sentence at the first breath', () => {
    /* the bug this was reported as: "set thermostat to seventy two degrees" came back as "set",
       because Chrome's own endpointer ends the turn at the first pause. The house waits instead. */
    at('?listen=browser')
    listen(listener)
    const r = FakeSpeech.last!
    r.onresult!(said('set'))
    vi.advanceTimersByTime(1000) // a breath, not the end of a sentence
    expect(heard, 'it gave up mid-sentence').toEqual([])
    r.onresult!(said('set', ' thermostat to seventy two degrees'))
    vi.advanceTimersByTime(1000)
    expect(heard).toEqual([])
    silence()
    expect(heard).toEqual(['set thermostat to seventy two degrees'])
  })

  it('waits for you to start, because a tap is not a promise to speak at once', () => {
    at('?listen=browser')
    listen(listener)
    vi.advanceTimersByTime(4000) // crossing the room, or thinking
    expect(heard, 'it gave up before anybody had said anything').toEqual([])
    FakeSpeech.last!.onresult!(said('good night'))
    silence()
    expect(heard).toEqual(['good night'])
  })

  it('does eventually stop listening to a room that never says anything', () => {
    at('?listen=browser')
    listen(listener)
    vi.advanceTimersByTime(6500)
    expect(heard).toEqual(['(ended)'])
  })

  it('shows the words as they arrive, so a long sentence keeps the house visibly listening', () => {
    at('?listen=browser')
    const sofar: string[] = []
    listen({ ...listener, hearing: (s: string) => sofar.push(s) })
    FakeSpeech.last!.onresult!(said('set thermostat'))
    FakeSpeech.last!.onresult!(said('set thermostat', ' to seventy two'))
    expect(sofar).toEqual(['set thermostat', 'set thermostat to seventy two'])
  })

  it('ignores a browser saying no-speech while the house is still waiting', () => {
    at('?listen=browser')
    listen(listener)
    FakeSpeech.last!.onerror!({ error: 'no-speech' })
    expect(heard, 'a quiet moment was treated as an answer').toEqual([])
    FakeSpeech.last!.onresult!(said('lock up'))
    silence()
    expect(heard).toEqual(['lock up'])
  })

  it('takes what there is when the browser gives up before the house does', () => {
    at('?listen=browser')
    listen(listener)
    FakeSpeech.last!.onresult!(said('good night'))
    FakeSpeech.last!.onend!()
    expect(heard).toEqual(['good night'])
  })

  it('says why in words a person can act on, rather than going quiet', () => {
    at('?listen=browser')
    listen(listener)
    FakeSpeech.last!.onerror!({ error: 'not-allowed' })
    expect(heard[0]).toMatch(/Allow the microphone/)
  })

  it('names the cloud when a recogniser goes looking for one', () => {
    /* the error docs/voice.md cares about most: it means the audio was leaving the house */
    at('?listen=browser')
    listen(listener)
    FakeSpeech.last!.onerror!({ error: 'network' })
    expect(heard[0]).toMatch(/sends speech away/)
  })

  it('does not scold somebody for stopping it', () => {
    at('?listen=browser')
    listen(listener)
    FakeSpeech.last!.onerror!({ error: 'aborted' })
    expect(heard).toEqual(['(ended)'])
  })

  it('falls back once when there is no on-device model, and says the audio is leaving', () => {
    /* Chrome offers `processLocally` and then refuses it until the model has been fetched, which on
       a machine that has never used this API is every time. Without the second go the flag is
       useless on the machine most likely to be running it. */
    at('?listen=browser')
    listen(listener)
    const asked = FakeSpeech.last!
    expect(asked.processLocally).toBe(true)
    asked.onerror!({ error: 'language-not-supported' })
    expect(FakeSpeech.last, 'it did not try again').not.toBe(asked)
    expect(FakeSpeech.last!.started).toBe(true)
    expect(FakeSpeech.last!.processLocally).toBeUndefined()
    expect(heard, 'it gave up instead of falling back').toEqual([])
    expect(console.warn).toHaveBeenCalledWith(expect.stringMatching(/LEAVING THIS MACHINE/))
    FakeSpeech.last!.onresult!(said('lock up'))
    silence()
    expect(heard).toEqual(['lock up'])
  })

  it('will not fall back when the cloud has been refused outright', () => {
    at('?listen=browser-local')
    listen(listener)
    const asked = FakeSpeech.last!
    asked.onerror!({ error: 'language-not-supported' })
    expect(FakeSpeech.last, 'it went to the cloud anyway').toBe(asked)
    expect(heard[0]).toMatch(/no on-device model/)
  })

  it('answers no where there is no Web Speech API at all, which is the wall', () => {
    at('?listen=browser')
    vi.stubGlobal('SpeechRecognition', undefined)
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    expect(canListen()).toBe(false)
    expect(listen(listener)).toBeNull()
  })
})
