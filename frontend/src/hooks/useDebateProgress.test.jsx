import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as tickersApi from '../api/tickers'
import { useDebateProgress } from './useDebateProgress'

const progress = (stage) => ({ ticker: 'VCB', running: true, stage, elapsed_ms: 100 })

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  return { wrapper }
}

// The second argument is when the run started (the mutation's submission time), or null when no
// run is pending: polling follows it, and so does the cache entry, so a new run never shows the
// last run's stage.
const render = (wrapper, startedAt) =>
  renderHook(({ started }) => useDebateProgress('VCB', started), { initialProps: { started: startedAt }, wrapper })

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useDebateProgress', () => {
  it('does not poll while no run is pending', async () => {
    const { wrapper } = setup()
    const poll = vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue(progress('round1'))

    render(wrapper, null)
    await vi.advanceTimersByTimeAsync(10_000)

    expect(poll).not.toHaveBeenCalled()
  })

  it('polls at once and then every 2 seconds while a run is pending', async () => {
    const { wrapper } = setup()
    const poll = vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue(progress('round1'))

    const { result } = render(wrapper, 1000)
    await vi.advanceTimersByTimeAsync(10)
    expect(poll).toHaveBeenCalledTimes(1)
    expect(poll).toHaveBeenCalledWith('VCB')
    expect(result.current.data).toEqual(progress('round1'))

    await vi.advanceTimersByTimeAsync(2000)
    expect(poll).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(2000)
    expect(poll).toHaveBeenCalledTimes(3)
  })

  it('stops polling when the run ends', async () => {
    const { wrapper } = setup()
    const poll = vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue(progress('round1'))
    const { rerender } = render(wrapper, 1000)
    await vi.advanceTimersByTimeAsync(2100)
    const calls = poll.mock.calls.length

    rerender({ started: null })
    await vi.advanceTimersByTimeAsync(10_000)

    expect(poll).toHaveBeenCalledTimes(calls)
  })

  it('keeps the last value when a poll fails', async () => {
    const { wrapper } = setup()
    const poll = vi.spyOn(tickersApi, 'getDebateProgress')
      .mockResolvedValueOnce(progress('round2'))
      .mockRejectedValue(new Error('network'))

    const { result } = render(wrapper, 1000)
    await vi.advanceTimersByTimeAsync(10)
    expect(result.current.data).toEqual(progress('round2'))

    await vi.advanceTimersByTimeAsync(2000)

    expect(poll).toHaveBeenCalledTimes(2)
    expect(result.current.data).toEqual(progress('round2'))
  })

  it('a new run does not start with the last run\'s stage', async () => {
    const { wrapper } = setup()
    vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue(progress('synthesis'))
    const { result, rerender } = render(wrapper, 1000)
    await vi.advanceTimersByTimeAsync(10)
    expect(result.current.data.stage).toBe('synthesis')
    rerender({ started: null })

    rerender({ started: 5000 }) // the next run, before its first poll has answered

    expect(result.current.data).toBeUndefined()
  })
})
