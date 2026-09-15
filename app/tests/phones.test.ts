/* Who this screen is, as far as the phones go.

   The house answers /phones with what THIS phone may see, so the panel works out nothing about who is
   allowed what -- it reads the row the hub keeps for it. These hold the two places that still matters
   on this side: the live nudge has to be followed by asking (it no longer carries the roster, because
   one message goes to every panel at once), and the word for what this screen may do comes off `how`. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Phone } from '../src/api'

const getPhones = vi.fn()
vi.mock('../src/api', async (original) => ({ ...(await original<object>()), getPhones }))

const { holdsKeys, loadPhones, store } = await import('../src/store')

const phone = (how: Phone['how'], me = false, id = how): Phone =>
  ({ id, name: id, kind: 'phone', joined: 0, expires: null, remote: false, last_seen: null, how, me })

beforeEach(() => {
  getPhones.mockReset()
  store.phones = []; store.asks = []
  store.status = { locked: true } as any
})

describe('what this screen may do with the phones', () => {
  it('is the house set up on it, or the code typed on it', () => {
    for (const how of ['setup', 'code'] as const) {
      store.phones = [phone(how, true)]
      expect(holdsKeys()).toBe(true)
    }
  })

  it('is not being let in at the wall, which is a way in and not a key', () => {
    store.phones = [phone('wall', true)]
    expect(holdsKeys()).toBe(false)
  })

  it('reads its own row, not somebody else\'s', () => {
    store.phones = [phone('setup', false, 'the wall'), phone('wall', true, 'mine')]
    expect(holdsKeys()).toBe(false)
  })

  it('is everything, in a house with no code: there is no door to keep', () => {
    store.status = { locked: false } as any
    expect(holdsKeys()).toBe(true)
  })
})

describe('the roster', () => {
  it('is asked for when the hub says it changed, rather than arriving with the news', async () => {
    getPhones.mockResolvedValue({ phones: [phone('setup', true)], asks: [{ id: 'a1', name: 'Sam', kind: 'phone', asked: 0 }] })
    await loadPhones(true)
    expect(getPhones).toHaveBeenCalled()
    expect(store.asks).toHaveLength(1)
  })

  it('is left alone when the house has no code, because then it has no phones', async () => {
    store.status = { locked: false } as any
    store.phones = [phone('setup', true)]
    await loadPhones()
    expect(getPhones).not.toHaveBeenCalled()
    expect(store.phones).toEqual([])
  })

  it('keeps the phones it had when the hub does not answer', async () => {
    store.phones = [phone('setup', true)]
    getPhones.mockRejectedValue(new Error('down'))
    await loadPhones(true)
    expect(store.phones).toHaveLength(1)
  })
})
