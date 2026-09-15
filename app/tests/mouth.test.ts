/* Where a spoken answer comes out.

   `ear.test.ts`'s opposite number, and it starts the same way: with the DEGRADATION. No house has a
   voice yet, so a reply carries no clip, and the panel must do nothing at all rather than reach for
   the browser's own voice -- which on several platforms is a vendor's, and on some of them a network
   call, and would break *works with the internet down* without anybody noticing. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { speak, hush } from '../src/mouth'

const at = (search: string) => vi.stubGlobal('location', { ...window.location, search })

/* One fake Audio for the page, recording what it was asked to play. */
const played: string[] = []
let last: { src: string; paused: boolean }
class FakeAudio {
  src: string
  paused = false
  constructor(src: string) { this.src = src; played.push(src); last = this }
  play() { return Promise.resolve() }
  pause() { this.paused = true }
  addEventListener() {}
}

const said: string[] = []
const synth = { speak: (u: { text: string }) => said.push(u.text), cancel: () => said.push('(cancel)') }

afterEach(() => { hush(); played.length = 0; said.length = 0; vi.unstubAllGlobals() })

describe('a house with no voice, which is every house today', () => {
  it('says nothing at all rather than borrowing the browser\'s voice', () => {
    at('')
    vi.stubGlobal('Audio', FakeAudio)
    vi.stubGlobal('speechSynthesis', synth)
    expect(speak({ spoken: 'Front door is locked.' })).toBe(false)
    expect(played).toEqual([])
    expect(said).toEqual([])
  })

  it('is unbothered by a reply with nothing in it', () => {
    at('')
    vi.stubGlobal('Audio', FakeAudio)
    expect(speak(null)).toBe(false)
    expect(speak({})).toBe(false)
  })
})

describe('a hub that has synthesised the answer', () => {
  it('plays the clip the brain minted, and nothing else', () => {
    at('')
    vi.stubGlobal('Audio', FakeAudio)
    vi.stubGlobal('speechSynthesis', synth)
    expect(speak({ speak: { url: '/say/clip/abc', text: 'Front door is locked.' }, spoken: 'Front door is locked.' })).toBe(true)
    expect(played).toEqual(['/say/clip/abc'])
    expect(said).toEqual([])          // never the browser's voice when the house has its own
  })

  it('stops the last answer before starting the next, so two never overlap', () => {
    at('')
    vi.stubGlobal('Audio', FakeAudio)
    speak({ speak: { url: '/say/clip/one', text: 'one' } })
    const first = last
    speak({ speak: { url: '/say/clip/two', text: 'two' } })
    expect(first.paused).toBe(true)
    expect(played).toEqual(['/say/clip/one', '/say/clip/two'])
  })

  it('goes quiet when it is told to', () => {
    at('')
    vi.stubGlobal('Audio', FakeAudio)
    speak({ speak: { url: '/say/clip/one', text: 'one' } })
    hush()
    expect(last.paused).toBe(true)
  })
})

describe('the preview, for looking at this before there is a container to look at it with', () => {
  it('speaks the line the brain wrote, and only behind the flag', () => {
    at('?speak=browser')
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; lang = ''; onend = () => {}; constructor(t: string) { this.text = t } })
    expect(speak({ spoken: 'One of the two kitchen lights is on.' })).toBe(true)
    expect(said).toEqual(['One of the two kitchen lights is on.'])
  })

  it('still prefers the hub clip when there is one, because that is the real path', () => {
    at('?speak=browser')
    vi.stubGlobal('Audio', FakeAudio)
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; lang = ''; onend = () => {}; constructor(t: string) { this.text = t } })
    speak({ speak: { url: '/say/clip/abc', text: 'x' }, spoken: 'x' })
    expect(played).toEqual(['/say/clip/abc'])
    expect(said).toEqual([])
  })
})
