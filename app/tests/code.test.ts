/* The code on the settings, and the one chance to type it.

   This is the loop between the panel and the door: a request goes out, the house says "code", the
   panel asks, the request goes again. Getting it wrong either locks a family out of their own
   settings or keeps retrying against a house that has already said no. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { lock, remember, request } from '../src/code'

const answer = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

/** Types `code` into the prompt as soon as the panel puts one up; `null` presses Cancel. */
function typing(code: string | null) {
  const interval = setInterval(() => {
    if (!lock.prompt) return
    const { resolve } = lock.prompt
    lock.prompt = null
    if (code !== null) remember(code)
    resolve(code !== null)
  }, 1)
  return () => clearInterval(interval)
}

beforeEach(() => {
  remember('')
  lock.prompt = null
  lock.unpaired = false
  vi.restoreAllMocks()
})

describe('an ordinary request', () => {
  it('goes straight out and comes straight back', async () => {
    const fetchMock = vi.fn().mockResolvedValue(answer(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const r = await request('/home')
    expect(r.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('carries the code once the house has one, without being asked again', async () => {
    remember('4821')
    const fetchMock = vi.fn().mockResolvedValue(answer(200))
    vi.stubGlobal('fetch', fetchMock)
    await request('/rooms', { method: 'POST' })
    const headers = fetchMock.mock.calls[0][1].headers as Headers
    expect(headers.get('X-Hub-Code')).toBe('4821')
    expect(lock.prompt).toBeNull()
  })
})

describe('when the house asks for the code', () => {
  it('asks the person, then sends the request again with what they typed', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(answer(401, { detail: 'code' }))
      .mockResolvedValueOnce(answer(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const stop = typing('4821')
    const r = await request('/rooms', { method: 'POST' })
    stop()
    expect(r.status).toBe(200)
    expect((fetchMock.mock.calls[1][1].headers as Headers).get('X-Hub-Code')).toBe('4821')
  })

  it('gives up when the person cancels, rather than asking forever', async () => {
    const fetchMock = vi.fn().mockResolvedValue(answer(401, { detail: 'code' }))
    vi.stubGlobal('fetch', fetchMock)
    const stop = typing(null)
    await expect(request('/rooms', { method: 'POST' })).rejects.toThrow('That needs the code')
    stop()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops asking after a few wrong ones instead of looping on a house that keeps refusing', async () => {
    const fetchMock = vi.fn().mockResolvedValue(answer(401, { detail: 'code' }))
    vi.stubGlobal('fetch', fetchMock)
    const stop = typing('0000')
    const r = await request('/rooms', { method: 'POST' })
    stop()
    expect(r.status).toBe(401)
    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(5)
  })
})

describe('when this phone does not belong to the house', () => {
  it('puts the join screen up rather than asking for a code that would not help', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(answer(401, { detail: 'phone' })))
    await expect(request('/home')).rejects.toThrow('not in the house yet')
    expect(lock.unpaired).toBe(true)
    expect(lock.prompt).toBeNull()
  })
})

describe('a 401 that is about something else', () => {
  it('is handed back as it is rather than turned into a code prompt', async () => {
    const fetchMock = vi.fn().mockResolvedValue(answer(401, { detail: 'the engine refused the token' }))
    vi.stubGlobal('fetch', fetchMock)
    const r = await request('/setup/login', { method: 'POST' })
    expect(r.status).toBe(401)
    expect(lock.prompt).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('survives a 401 with no JSON in it at all', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 401 })))
    const r = await request('/home')
    expect(r.status).toBe(401)
  })
})

describe('remembering the code', () => {
  it('keeps it for this tab and forgets it when asked', async () => {
    remember('4821')
    const fetchMock = vi.fn().mockResolvedValue(answer(200))
    vi.stubGlobal('fetch', fetchMock)
    await request('/rooms', { method: 'POST' })
    expect((fetchMock.mock.calls[0][1].headers as Headers).get('X-Hub-Code')).toBe('4821')

    remember('')
    await request('/rooms', { method: 'POST' })
    expect((fetchMock.mock.calls[1][1].headers as Headers).get('X-Hub-Code')).toBeNull()
  })
})
