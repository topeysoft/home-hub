/* What a camera card is allowed to claim. The bug this holds shut: a Ring camera hands back the same
   frame for hours, and the panel dated the picture from the moment it fetched the bytes, so a dark 4am
   still wore a "Just now" chip at lunchtime. The age has to come off the frame, and a frame that is
   not changing must not be asked for every fifteen seconds. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ageLabel, BASE, SLOWEST, forget, fromLive, stillFor, watchStill } from '../src/still'

/** One answer from the still route. `age` is the seconds the brain says those bytes have been current. */
function frame(tag: string, age: number, status = 200) {
  return {
    ok: status < 400,
    status,
    headers: new Headers({ ETag: `"${tag}"`, 'X-Frame-Age': String(age) }),
    blob: async () => new Blob([tag], { type: 'image/jpeg' }),
  } as unknown as Response
}

let fetching: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-14T13:00:00'))
  fetching = vi.fn(async () => frame('a', 0))
  vi.stubGlobal('fetch', fetching)
  // happy-dom has no object URLs, and the test only cares that one frame is told from another.
  let n = 0
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => `blob:${++n}`, revokeObjectURL: () => {} }))
})
afterEach(() => { forget(); vi.useRealTimers(); vi.unstubAllGlobals() })

/** Let the poll that is in flight finish. */
const settle = async () => { await vi.advanceTimersByTimeAsync(0) }

describe('how old the picture is', () => {
  it('reads the age off the frame, not off the fetch', async () => {
    fetching.mockResolvedValue(frame('night', 4 * 3600))    // the brain: these bytes have been the answer since 9am
    watchStill('camera.door')
    await settle()
    // The panel asked for it a second ago. The picture is still four hours old and has to say so.
    expect(ageLabel(Date.now() - 4 * 3600 * 1000)).toBe('4h ago')
  })

  it('has words for every distance a camera can be out of date', () => {
    const now = Date.now()
    expect(ageLabel(now - 1000, now)).toBe('Just now')
    expect(ageLabel(now - 12_000, now)).toBe('12s ago')
    expect(ageLabel(now - 9 * 60_000, now)).toBe('9m ago')
    expect(ageLabel(now - 4 * 3600_000, now)).toBe('4h ago')
    expect(ageLabel(now - 50 * 3600_000, now)).toBe('2d ago')
  })
})

describe('asking for it again', () => {
  it('backs off while the frame is not changing, and hurries the moment it is', async () => {
    fetching.mockResolvedValue(frame('same', 60))
    watchStill('camera.door')
    await settle()
    expect(fetching).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(BASE)          // same bytes: wait twice as long next time
    expect(fetching).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(BASE)
    expect(fetching).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(BASE)
    expect(fetching).toHaveBeenCalledTimes(3)

    fetching.mockResolvedValue(frame('moved', 0))    // something happened: back to the eager pace
    await vi.advanceTimersByTimeAsync(4 * BASE)
    const after = fetching.mock.calls.length
    await vi.advanceTimersByTimeAsync(BASE)
    expect(fetching.mock.calls.length).toBeGreaterThan(after)
  })

  it('never waits longer than SLOWEST, however long nothing happens', async () => {
    fetching.mockResolvedValue(frame('same', 60))
    watchStill('camera.door')
    await settle()
    await vi.advanceTimersByTimeAsync(60 * 60_000)   // an hour of a camera looking at an empty drive
    const idle = fetching.mock.calls.length
    await vi.advanceTimersByTimeAsync(SLOWEST)
    expect(fetching.mock.calls.length).toBe(idle + 1)
  })

  it('offers the frame it holds so the brain can answer with a header', async () => {
    watchStill('camera.door')
    await settle()
    expect(fetching.mock.calls[0][1].headers['If-None-Match']).toBeUndefined()
    await vi.advanceTimersByTimeAsync(BASE)
    expect(fetching.mock.calls[1][1].headers['If-None-Match']).toBe('"a"')
  })

  /* The age the brain quotes is "unchanged for", which a restart resets -- it has only just started
     watching and cannot know the frame is old. This is the line that keeps that from reaching a
     screen: a panel that still holds the frame gets a 304, and a 304 never re-dates anything. So a
     hub restart cannot make a four-hour-old picture read "Just now" under a panel that is up. */
  it('keeps the age it knows when the brain has forgotten it', async () => {
    fetching.mockResolvedValue(frame('night', 4 * 3600))
    watchStill('camera.door')
    await settle()
    const dated = stillFor('camera.door').at
    expect(ageLabel(dated)).toBe('4h ago')

    // the hub restarts: same bytes, so the ETag still matches and the answer is a 304 -- carrying an
    // age of 0, because the brain is watching these bytes for the first time
    fetching.mockResolvedValue({ ok: false, status: 304, headers: new Headers({ 'X-Frame-Age': '0' }), blob: async () => new Blob() } as unknown as Response)
    await vi.advanceTimersByTimeAsync(BASE)
    expect(stillFor('camera.door').at, 'a 304 re-dated the picture').toBe(dated)
    expect(ageLabel(stillFor('camera.door').at)).toBe('4h ago')
  })

  it('takes 304 for the answer it is: the picture we have is still the picture', async () => {
    watchStill('camera.door')
    await settle()
    fetching.mockResolvedValue({ ok: false, status: 304, headers: new Headers(), blob: async () => new Blob() } as unknown as Response)
    await vi.advanceTimersByTimeAsync(BASE)
    await vi.advanceTimersByTimeAsync(2 * BASE)
    expect(fetching).toHaveBeenCalledTimes(3)        // a 304 is an unchanged frame, so it backs off too
  })
})

describe('one camera, however many cards', () => {
  it('fetches once for every surface showing it, and stops when the last one goes', async () => {
    const a = watchStill('camera.door'), b = watchStill('camera.door')
    await settle()
    expect(fetching).toHaveBeenCalledTimes(1)        // the room card and the tile are one watch

    a()
    await vi.advanceTimersByTimeAsync(BASE)
    expect(fetching).toHaveBeenCalledTimes(2)        // b is still looking

    b()
    await vi.advanceTimersByTimeAsync(10 * BASE)
    expect(fetching).toHaveBeenCalledTimes(2)        // nobody is looking: nothing is asked of the camera
  })
})

describe('a frame off the live picture', () => {
  /* happy-dom draws nothing, so the canvas is stood in for: what is under test is which frame wins,
     not the JPEG. */
  function stubCanvas(blob: Blob | null = new Blob(['live'], { type: 'image/jpeg' })) {
    const made = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag !== 'canvas') return made(tag)
      return { width: 0, height: 0, getContext: () => ({ drawImage: () => {} }), toBlob: (cb: BlobCallback) => cb(blob) } as unknown as HTMLCanvasElement
    })
  }
  const video = { videoWidth: 1280, videoHeight: 720 } as HTMLVideoElement

  it('is the picture the cards show, because it is the newest one there is', async () => {
    fetching.mockResolvedValue(frame('night', 4 * 3600))      // the still route is still handing out last night
    watchStill('camera.door')
    await settle()
    expect(stillFor('camera.door').live).toBe(false)

    stubCanvas()
    fromLive('camera.door', video)
    await settle()
    const now = stillFor('camera.door')
    expect(now.live).toBe(true)
    expect(ageLabel(now.at)).toBe('Just now')
  })

  it('is not painted over by a still route that is four hours behind it', async () => {
    stubCanvas()
    fromLive('camera.door', video)
    await settle()
    const live = stillFor('camera.door').url

    fetching.mockResolvedValue(frame('night', 4 * 3600))
    watchStill('camera.door')
    await settle()
    expect(stillFor('camera.door').url).toBe(live)
    expect(stillFor('camera.door').live).toBe(true)
  })

  it('gives way to a still that is genuinely newer', async () => {
    stubCanvas()
    fromLive('camera.door', video)
    await settle()
    vi.setSystemTime(Date.now() + 10 * 60_000)                // ten minutes after the viewer was closed
    fetching.mockResolvedValue(frame('morning', 0))           // and the camera has just seen something
    watchStill('camera.door')
    await settle()
    expect(stillFor('camera.door').live).toBe(false)
    expect(ageLabel(stillFor('camera.door').at)).toBe('Just now')
  })
})
