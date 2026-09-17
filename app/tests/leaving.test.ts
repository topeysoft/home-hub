/* A card leaving the Home row, on the two clocks it actually runs on: timeouts that keep firing
   while the screen is off, and animation frames that do not. The frames here are a queue that is
   only ever flushed by hand, which is what a screen that is off looks like from the inside. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FADE, SHOWN, SPARE, leave, type Marks } from '../src/leaving'

let frames: FrameRequestCallback[]
beforeEach(() => {
  vi.useFakeTimers()
  frames = []
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { frames.push(cb); return frames.length })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

/* two frames, the way the browser would run them when the screen is on */
function paint() { for (let i = 0; i < 2; i++) { const cbs = frames; frames = []; for (const cb of cbs) cb(0) } }

describe('a card leaving the row', () => {
  it('is going now, gone after the beat, and swept once the fade has had its time', () => {
    const going: Marks = {}, gone: Marks = {}
    const swept = vi.fn()
    leave('lamp', going, gone, swept)
    expect(going).toEqual({ lamp: true }); expect(gone).toEqual({})

    vi.advanceTimersByTime(SHOWN); paint()
    expect(gone).toEqual({ lamp: true })
    expect(swept).not.toHaveBeenCalled()

    vi.advanceTimersByTime(FADE + SPARE)
    expect(going).toEqual({}); expect(gone).toEqual({})
    expect(swept).toHaveBeenCalledTimes(1)
  })

  it('leaves no mark when the frames arrive after the sweep, as they do after a screen was off', () => {
    const going: Marks = {}, gone: Marks = {}
    leave('speaker', going, gone, () => {})
    /* the screen goes off: the beat and the sweep both fire, and no frame is painted between them */
    vi.advanceTimersByTime(SHOWN + FADE + SPARE)
    expect(going).toEqual({}); expect(gone).toEqual({})
    /* the screen comes back, and the frames the beat asked for finally run */
    paint()
    expect(gone).toEqual({})
  })
})
