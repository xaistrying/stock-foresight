import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTickerContext } from './useTickerContext'
import * as tickersApi from '../api/tickers'
import { ApiError } from '../api/client'
import { catalogEntry, ineligible, newQueryClient } from '../test/railFixtures'

const HISTORY = {
  ticker: 'TCB',
  rows: [
    { date: '2026-10-05', open: 41, high: 43, low: 40, close: 42, volume: 100 },
    { date: '2026-10-06', open: 42, high: 43, low: 41, close: 42.55, volume: 120 },
  ],
}
const range = (overrides = {}) => ({
  ticker: 'TCB', as_of: '2026-10-06', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
  range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 }, ...overrides,
})

function arrange({ catalog = [], historyResult = HISTORY, rangeResult = range() } = {}) {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: catalog })
  const history = vi.spyOn(tickersApi, 'fetchTickerHistory')
  const rangeSpy = vi.spyOn(tickersApi, 'fetchTickerRange')
  if (historyResult instanceof Error) history.mockRejectedValue(historyResult)
  else history.mockResolvedValue(historyResult)
  if (rangeResult instanceof Error) rangeSpy.mockRejectedValue(rangeResult)
  else rangeSpy.mockResolvedValue(rangeResult)
  return { history, range: rangeSpy }
}

function renderContext(ticker) {
  const queryClient = newQueryClient()
  return renderHook(() => useTickerContext(ticker), {
    wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>,
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useTickerContext', () => {
  it('is empty when no ticker is selected, and requests nothing but the catalog', async () => {
    const spies = arrange()

    const { result } = renderContext(null)

    expect(result.current).toEqual({
      asOf: null, ageSessions: null, stale: false, reasons: [], eligible: null, lastClose: null,
    })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(spies.history).not.toHaveBeenCalled()
    expect(spies.range).not.toHaveBeenCalled()
  })

  it('takes the age and the reasons from the catalog entry, the date from /range and the close from /history', async () => {
    arrange({ catalog: [catalogEntry('TCB')] })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.lastClose).toBe(42.55))
    await waitFor(() => expect(result.current.ageSessions).toBe(0))
    expect(result.current).toEqual({
      asOf: '2026-10-06', ageSessions: 0, stale: false, reasons: [], eligible: true, lastClose: 42.55,
    })
  })

  it('reports a stale catalog ticker with its age and reasons, from the server and nothing else', async () => {
    arrange({
      catalog: [catalogEntry('TCB', { eligibility: ineligible(['stale'], 21) })],
      rangeResult: range({ as_of: '2026-09-07', status: 'ineligible', range_5s_pct: null, reasons: ['stale'] }),
    })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.ageSessions).toBe(21))
    expect(result.current).toMatchObject({
      asOf: '2026-09-07', ageSessions: 21, stale: true, reasons: ['stale'], eligible: false,
    })
  })

  it('is stale exactly when the reasons say so: a large age alone is not enough', async () => {
    arrange({
      catalog: [
        catalogEntry('TCB', { eligibility: { eligible: true, reasons: [], as_of: '2026-09-01', age_sessions: 40 } }),
      ],
    })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.ageSessions).toBe(40))
    expect(result.current.stale).toBe(false)
  })

  it('is stale when a delisted ticker is also stale', async () => {
    arrange({ catalog: [catalogEntry('TCB', { eligibility: ineligible(['delisted', 'stale'], 24) })] })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.reasons).toEqual(['delisted', 'stale']))
    expect(result.current.stale).toBe(true)
  })

  it('gives a searched-in ticker (no catalog entry) no age, and takes stale from /range', async () => {
    arrange({
      catalog: [],
      rangeResult: range({ as_of: '2026-09-07', status: 'ineligible', range_5s_pct: null, reasons: ['stale'] }),
    })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.asOf).toBe('2026-09-07'))
    expect(result.current.ageSessions).toBeNull()
    expect(result.current.stale).toBe(true)
    expect(result.current.reasons).toEqual(['stale'])
    expect(result.current.eligible).toBe(false)
  })

  it('treats a searched-in ticker whose /range serves a band as eligible', async () => {
    arrange({ catalog: [] })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.asOf).toBe('2026-10-06'))
    expect(result.current).toMatchObject({ ageSessions: null, stale: false, eligible: true })
  })

  it('treats a catalog entry with no eligibility (an older backend) like an entry with none: /range answers', async () => {
    arrange({ catalog: [catalogEntry('TCB', { eligibility: null })] })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.asOf).toBe('2026-10-06'))
    expect(result.current.ageSessions).toBeNull()
  })

  it('falls back to the last history date when /range fails', async () => {
    arrange({
      catalog: [catalogEntry('TCB')],
      rangeResult: new ApiError('boom', { status: 503 }),
    })

    const { result } = renderContext('TCB')

    await waitFor(() => expect(result.current.asOf).toBe('2026-10-06'))
    expect(result.current.lastClose).toBe(42.55)
  })

  it('has no close and no date when nothing is loaded for the ticker (404)', async () => {
    arrange({
      catalog: [],
      historyResult: new ApiError('nope', { status: 404 }),
      rangeResult: new ApiError('nope', { status: 404 }),
    })

    const { result } = renderContext('TCB')

    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(result.current).toMatchObject({ asOf: null, lastClose: null, eligible: null })
  })

  it('asks for the selected ticker\'s history and range once each, and for no other ticker', async () => {
    const spies = arrange({ catalog: [catalogEntry('TCB'), catalogEntry('VIB')] })

    renderContext('TCB')
    renderHook(() => useTickerContext('TCB'), {
      wrapper: ({ children }) => <QueryClientProvider client={newQueryClient()}>{children}</QueryClientProvider>,
    })

    await waitFor(() => expect(spies.history).toHaveBeenCalled())
    expect(spies.history.mock.calls.every(([ticker]) => ticker === 'TCB')).toBe(true)
    expect(spies.range.mock.calls.every(([ticker]) => ticker === 'TCB')).toBe(true)
  })
})
