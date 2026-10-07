import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as tickersApi from '../api/tickers'
import { useTickerRange } from './useTickerRange'

function wrapper({ children }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useTickerRange', () => {
  it('fetches /range for the selected ticker', async () => {
    const spy = vi
      .spyOn(tickersApi, 'fetchTickerRange')
      .mockResolvedValue({ ticker: 'TCB', status: 'ok', range_5s_pct: 3.2 })

    const { result } = renderHook(() => useTickerRange('TCB'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalledWith('TCB')
    expect(result.current.data.range_5s_pct).toBe(3.2)
  })

  it('is disabled, and fetches nothing, when no ticker is selected', async () => {
    const spy = vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({})

    const { result } = renderHook(() => useTickerRange(null), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(spy).not.toHaveBeenCalled()
  })
})
