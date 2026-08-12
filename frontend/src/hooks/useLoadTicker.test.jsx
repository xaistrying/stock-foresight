import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useIsTickerLoading, useLoadTicker } from './useLoadTicker'
import * as tickersApi from '../api/tickers'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useIsTickerLoading', () => {
  // ticker-manual-refresh: the Refresh action and the original
  // load-on-first-select flow are two independent useLoadTicker(ticker)
  // call sites for the same ticker (design.md Decision 3) — this confirms
  // useIsTickerLoading observes the shared mutation cache rather than one
  // hook instance's local state, so a load started by one caller disables
  // every other caller watching the same ticker.
  it('reflects a mutation started by a different useLoadTicker(ticker) instance for the same ticker', async () => {
    let resolveLoad
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(
      new Promise((resolve) => {
        resolveLoad = resolve
      }),
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result: triggerResult } = renderHook(() => useLoadTicker('TCB'), { wrapper })
    const { result: observerResult } = renderHook(() => useIsTickerLoading('TCB'), { wrapper })

    expect(observerResult.current).toBe(false)

    act(() => {
      triggerResult.current.mutate()
    })

    await waitFor(() => expect(observerResult.current).toBe(true))

    resolveLoad({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })
    await waitFor(() => expect(observerResult.current).toBe(false))
  })

  it('does not reflect a mutation for a different ticker', async () => {
    let resolveLoad
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(
      new Promise((resolve) => {
        resolveLoad = resolve
      }),
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result: triggerResult } = renderHook(() => useLoadTicker('TCB'), { wrapper })
    const { result: observerResult } = renderHook(() => useIsTickerLoading('VIB'), { wrapper })

    act(() => {
      triggerResult.current.mutate()
    })

    expect(observerResult.current).toBe(false)
    resolveLoad({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })
  })
})

describe('useLoadTicker', () => {
  it('invalidates tickers/history/prediction/insight on a successful load', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useLoadTicker('TCB'), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    })

    act(() => {
      result.current.mutate()
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const invalidatedKeys = invalidateSpy.mock.calls.map((call) => call[0].queryKey)
    expect(invalidatedKeys).toEqual(
      expect.arrayContaining([
        ['tickers'],
        ['ticker-history', 'TCB'],
        ['ticker-prediction', 'TCB'],
        ['ticker-insight', 'TCB'],
      ]),
    )
  })

  it('does not invalidate any query on a non-ok status', async () => {
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'rate_limited' })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useLoadTicker('TCB'), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    })

    act(() => {
      result.current.mutate()
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
