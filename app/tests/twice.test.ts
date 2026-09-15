/* The two things the panel asks twice about, and why there are only two.

   Almost everything here happens on one tap and that is the product: a tile is a switch on a wall,
   and a switch on a wall does not interview you. The exceptions are the two where the failure mode
   of a stray finger is not a lamp -- opening a way into the house, and making a noise nobody can
   take back. A siren reaches this house as a `switch`, so until somebody says it is an alarm it
   wears a plug's tile and goes off on the first tap; that is the accident this file is about. */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { ARM_FOR, asksTwice, useArm } from '../src/twice'

describe('which way round the rule goes', () => {
  it('asks before it opens a way into the house, and before it makes a noise', () => {
    expect(asksTwice('lock', 'unlock')).toBe('Tap again to unlock')
    expect(asksTwice('alarm', 'on')).toBe('Tap again to sound')
  })
  it('never asks before making a house safer or quieter -- that half is always one tap', () => {
    expect(asksTwice('lock', 'lock')).toBeNull()
    expect(asksTwice('alarm', 'off')).toBeNull()
  })
  it('leaves everything else alone, so a lamp is still a lamp', () => {
    for (const k of ['light', 'switch', 'fan', 'media', 'cover', 'climate', 'vacuum'])
      for (const a of ['on', 'off', 'open', 'close', 'play', 'start'])
        expect(asksTwice(k, a)).toBeNull()
  })
  it('reads what the thing is SHOWN as: the siren is a switch entity underneath, and that is the point', () => {
    expect(asksTwice('switch', 'on')).toBeNull()      // nobody has said what this is yet
    expect(asksTwice('alarm', 'on')).not.toBeNull()   // somebody has
  })
})

describe('one armed control', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  const arm = () => { const a = useArm(); const go = vi.fn(); return { ...a, go } }

  it('does not sound an alarm on the first tap, and says what the second one will do', () => {
    const { armed, tap, go } = arm()
    expect(tap('alarm', 'on', go)).toBe(false)
    expect(go).not.toHaveBeenCalled()
    expect(armed.value).toBe('Tap again to sound')
  })

  it('sounds it on the second, and puts its words away again', () => {
    const { armed, tap, go } = arm()
    tap('alarm', 'on', go)
    expect(tap('alarm', 'on', go)).toBe(true)
    expect(go).toHaveBeenCalledTimes(1)
    expect(armed.value).toBeNull()
  })

  it('forgets after three seconds, so a tile left armed on a wall is not a loaded button an hour later', () => {
    const { armed, tap, go } = arm()
    tap('alarm', 'on', go)
    vi.advanceTimersByTime(ARM_FOR + 1)
    expect(armed.value).toBeNull()
    expect(tap('alarm', 'on', go)).toBe(false)     // the next tap is a first tap again
    expect(go).not.toHaveBeenCalled()
  })

  it('silences on the first tap even while it is armed to sound: quiet is never made to wait', () => {
    const { tap, go } = arm()
    tap('alarm', 'on', go)                          // armed, and then the thing goes off by itself
    expect(tap('alarm', 'off', go)).toBe(true)
    expect(go).toHaveBeenCalledTimes(1)
  })

  it('does it at once for everything that is not one of the two', () => {
    const { armed, tap, go } = arm()
    expect(tap('switch', 'on', go)).toBe(true)
    expect(go).toHaveBeenCalledTimes(1)
    expect(armed.value).toBeNull()
  })

  it('arms the door the same way, which is the behaviour this was lifted out of', () => {
    const { tap, go } = arm()
    expect(tap('lock', 'unlock', go)).toBe(false)
    expect(tap('lock', 'unlock', go)).toBe(true)
    expect(go).toHaveBeenCalledTimes(1)
  })
})
