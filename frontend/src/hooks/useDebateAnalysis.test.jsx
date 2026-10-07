import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as tickersApi from '../api/tickers'
import { ApiError } from '../api/client'
import { useDebateAnalysis } from './useDebateAnalysis'

const RESULT = { ticker: 'VCB', verdict: 'BUY_SIGNAL', synthesis: { key_tension: 'a tension' } }
const OTHER_RESULT = { ticker: 'VCB', verdict: 'OBSERVE', synthesis: { key_tension: 'another tension' } }

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  return { queryClient, wrapper }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useDebateAnalysis', () => {
  it('starts with nothing: no result, not pending, no error', () => {
    const { wrapper } = setup()

    const { result } = renderHook(() => useDebateAnalysis('VCB'), { wrapper })

    expect(result.current).toMatchObject({
      result: null, completedAt: null, isPending: false, startedAt: null, error: null,
    })
  })

  it('stores a successful result per ticker, with the time it finished', async () => {
    const { queryClient, wrapper } = setup()
    const run = vi.spyOn(tickersApi, 'runDebateAnalysis').mockResolvedValue(RESULT)
    const { result } = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    const before = Date.now()

    act(() => result.current.analyse())
    await waitFor(() => expect(result.current.result).toEqual(RESULT))

    expect(run).toHaveBeenCalledWith('VCB')
    expect(result.current.completedAt).toBeGreaterThanOrEqual(before)
    expect(result.current.isPending).toBe(false)
    expect(queryClient.getQueryData(['debate-result', 'VCB'])).toEqual({
      result: RESULT, completedAt: result.current.completedAt,
    })
  })

  it('keeps a result for ever: the cache entry is never garbage collected', async () => {
    const { queryClient, wrapper } = setup()
    vi.spyOn(tickersApi, 'runDebateAnalysis').mockResolvedValue(RESULT)
    const { result, unmount } = renderHook(() => useDebateAnalysis('VCB'), { wrapper })

    act(() => result.current.analyse())
    await waitFor(() => expect(result.current.result).toEqual(RESULT))
    unmount()

    expect(queryClient.getQueryCache().find({ queryKey: ['debate-result', 'VCB'] }).gcTime).toBe(Infinity)
  })

  it('is keyed by ticker: one ticker\'s result never shows for another', async () => {
    const { wrapper } = setup()
    vi.spyOn(tickersApi, 'runDebateAnalysis').mockResolvedValue(RESULT)
    const vcb = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    const fpt = renderHook(() => useDebateAnalysis('FPT'), { wrapper })

    act(() => vcb.result.current.analyse())
    await waitFor(() => expect(vcb.result.current.result).toEqual(RESULT))

    expect(fpt.result.current.result).toBeNull()
    expect(fpt.result.current.isPending).toBe(false)
  })

  it('makes pending state and start time readable per ticker after a remount', async () => {
    const { wrapper } = setup()
    const pending = deferred()
    vi.spyOn(tickersApi, 'runDebateAnalysis').mockReturnValue(pending.promise)
    const first = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    act(() => first.result.current.analyse())
    await waitFor(() => expect(first.result.current.isPending).toBe(true))
    first.unmount() // the user switched to another ticker

    const again = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    const other = renderHook(() => useDebateAnalysis('FPT'), { wrapper })

    expect(again.result.current.isPending).toBe(true)
    expect(typeof again.result.current.startedAt).toBe('number')
    expect(other.result.current.isPending).toBe(false)
    expect(other.result.current.startedAt).toBeNull()
    await act(async () => pending.resolve(RESULT))
  })

  it('does not abort on a ticker switch: the result lands in the cache and shows on return, with one request', async () => {
    const { queryClient, wrapper } = setup()
    const pending = deferred()
    const run = vi.spyOn(tickersApi, 'runDebateAnalysis').mockReturnValue(pending.promise)
    const first = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    act(() => first.result.current.analyse())
    first.unmount()

    await act(async () => pending.resolve(RESULT))

    expect(queryClient.getQueryData(['debate-result', 'VCB'])).toMatchObject({ result: RESULT })
    // It landed with nobody watching this ticker: it must still be exempt from garbage collection.
    expect(queryClient.getQueryCache().find({ queryKey: ['debate-result', 'VCB'] }).gcTime).toBe(Infinity)
    const back = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    expect(back.result.current.result).toEqual(RESULT)
    expect(back.result.current.isPending).toBe(false)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('keeps the earlier result when a re-run fails and shows the error beside it; a later success clears it', async () => {
    const { wrapper } = setup()
    const run = vi.spyOn(tickersApi, 'runDebateAnalysis')
    run.mockResolvedValueOnce(RESULT)
      .mockRejectedValueOnce(new ApiError('Another analysis is already running; try again shortly.', {
        status: 429, body: { code: 'debate_busy' },
      }))
      .mockResolvedValueOnce(OTHER_RESULT)
    const { result } = renderHook(() => useDebateAnalysis('VCB'), { wrapper })

    act(() => result.current.analyse())
    await waitFor(() => expect(result.current.result).toEqual(RESULT))

    act(() => result.current.analyse())
    await waitFor(() => expect(result.current.error).not.toBeNull())
    expect(result.current.error.status).toBe(429)
    expect(result.current.result).toEqual(RESULT)
    expect(result.current.isPending).toBe(false)

    act(() => result.current.analyse())
    await waitFor(() => expect(result.current.result).toEqual(OTHER_RESULT))
    expect(result.current.error).toBeNull()
  })

  it('shows the error of a failed run again after a remount', async () => {
    const { wrapper } = setup()
    vi.spyOn(tickersApi, 'runDebateAnalysis').mockRejectedValue(new ApiError('boom', { status: 500 }))
    const first = renderHook(() => useDebateAnalysis('VCB'), { wrapper })
    act(() => first.result.current.analyse())
    await waitFor(() => expect(first.result.current.error).not.toBeNull())
    first.unmount()

    const again = renderHook(() => useDebateAnalysis('VCB'), { wrapper })

    expect(again.result.current.error.message).toBe('boom')
  })

  it('a second Analyse while one is running starts no second request of its own', async () => {
    const { wrapper } = setup()
    const pending = deferred()
    const run = vi.spyOn(tickersApi, 'runDebateAnalysis').mockReturnValue(pending.promise)
    const { result } = renderHook(() => useDebateAnalysis('VCB'), { wrapper })

    act(() => result.current.analyse())
    await waitFor(() => expect(result.current.isPending).toBe(true))
    act(() => result.current.analyse())

    expect(run).toHaveBeenCalledTimes(1)
    await act(async () => pending.resolve(RESULT))
  })
})
