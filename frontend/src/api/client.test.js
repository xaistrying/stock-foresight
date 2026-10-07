import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, post } from './client'
import { DEBATE_CLIENT_TIMEOUT_MS, getDebateProgress, runDebateAnalysis } from './tickers'

// fetch is stubbed per test; a fetch that is still waiting rejects with the signal's reason
// when it aborts, which is what a real fetch does.
function stubFetch(impl) {
  const fetchMock = vi.fn(impl)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const waitsForAbort = (_url, { signal }) =>
  new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason))
  })

const jsonResponse = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('request: abort signal and time limit', () => {
  it('forwards an AbortSignal to fetch', async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { ok: true }))
    const controller = new AbortController()

    await post('/x', undefined, { signal: controller.signal })

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('makes a timeout abort an ApiError flagged timedOut, not the network-error text', async () => {
    stubFetch(waitsForAbort)

    const failure = await post('/x', undefined, { signal: AbortSignal.timeout(20) }).catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.timedOut).toBe(true)
    expect(failure.message).not.toMatch(/could not reach the server/i)
    expect(failure.status).toBeUndefined()
  })

  it('also recognises a TimeoutError thrown by fetch itself', async () => {
    stubFetch(async () => {
      throw new DOMException('The operation timed out.', 'TimeoutError')
    })

    await expect(post('/x')).rejects.toMatchObject({ name: 'ApiError', timedOut: true })
  })

  it('also maps a timeout that strikes while the response body is being read', async () => {
    stubFetch(async () => ({
      ok: true,
      status: 200,
      text: async () => {
        throw new DOMException('The operation timed out.', 'TimeoutError')
      },
    }))

    await expect(post('/x')).rejects.toMatchObject({ name: 'ApiError', timedOut: true })
  })

  it('keeps the network-error text, and timedOut false, for a real network failure', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    const failure = await post('/x').catch((error) => error)

    expect(failure.message).toMatch(/could not reach the server/i)
    expect(failure.timedOut).toBe(false)
  })

  it('a manual abort is not reported as a time limit', async () => {
    stubFetch(waitsForAbort)
    const controller = new AbortController()
    const pending = post('/x', undefined, { signal: controller.signal }).catch((error) => error)

    controller.abort()
    const failure = await pending

    expect(failure.timedOut).toBe(false)
  })
})

describe('request: failures keep their status and machine-readable code', () => {
  it.each([
    [429, 'debate_busy', 'Another analysis is already running; try again shortly.'],
    [503, 'debate_not_configured', 'DEBATE_LLM_EFFORT is not valid.'],
    [504, 'debate_timeout', 'The analysis did not finish within 180 s.'],
  ])('%i keeps status, body.code and the server message', async (status, code, detail) => {
    stubFetch(async () => jsonResponse(status, { detail, code }))

    const failure = await post('/x').catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.status).toBe(status)
    expect(failure.body.code).toBe(code)
    expect(failure.message).toBe(detail)
    expect(failure.timedOut).toBe(false)
  })
})

describe('runDebateAnalysis', () => {
  it('posts to the debate endpoint with a signal that times out after the client limit', async () => {
    const timeout = vi.spyOn(AbortSignal, 'timeout')
    const fetchMock = stubFetch(async () => jsonResponse(200, { verdict: 'OBSERVE' }))

    await expect(runDebateAnalysis('VCB')).resolves.toEqual({ verdict: 'OBSERVE' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/tickers\/VCB\/debate$/)
    expect(init.method).toBe('POST')
    expect(init.signal).toBeInstanceOf(AbortSignal)
    expect(timeout).toHaveBeenCalledWith(DEBATE_CLIENT_TIMEOUT_MS)
  })

  it('has a client limit of 200 s: the server budget of 180 s plus 20 s for its 504 to arrive', () => {
    expect(DEBATE_CLIENT_TIMEOUT_MS).toBe(200_000)
  })

  it('takes the limit as a parameter, so a test does not wait 200 s', async () => {
    stubFetch(waitsForAbort)

    await expect(runDebateAnalysis('VCB', { timeoutMs: 30 })).rejects.toMatchObject({ timedOut: true })
  })

  it('uses a timer when AbortSignal.timeout does not exist', async () => {
    vi.useFakeTimers()
    const original = AbortSignal.timeout
    AbortSignal.timeout = undefined
    try {
      stubFetch(waitsForAbort)
      const failure = runDebateAnalysis('VCB', { timeoutMs: 1000 }).catch((error) => error)

      await vi.advanceTimersByTimeAsync(1000)

      expect((await failure).timedOut).toBe(true)
    } finally {
      AbortSignal.timeout = original
    }
  })

  it('leaves no timer behind after a request that succeeded, even without AbortSignal.timeout', async () => {
    vi.useFakeTimers()
    const original = AbortSignal.timeout
    AbortSignal.timeout = undefined
    try {
      stubFetch(async () => jsonResponse(200, {}))

      await runDebateAnalysis('VCB', { timeoutMs: 200_000 })

      expect(vi.getTimerCount()).toBe(0)
    } finally {
      AbortSignal.timeout = original
    }
  })

  it('encodes the ticker in the path', async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, {}))

    await runDebateAnalysis('A B')

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/tickers\/A%20B\/debate$/)
  })
})

describe('getDebateProgress', () => {
  it('reads the progress endpoint', async () => {
    const fetchMock = stubFetch(async () =>
      jsonResponse(200, { ticker: 'VCB', running: true, stage: 'round2', elapsed_ms: 1200 }),
    )

    await expect(getDebateProgress('VCB')).resolves.toMatchObject({ running: true, stage: 'round2' })

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/tickers\/VCB\/debate\/progress$/)
  })
})
