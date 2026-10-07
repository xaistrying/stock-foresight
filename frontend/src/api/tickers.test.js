import { afterEach, describe, expect, it, vi } from 'vitest'
import { describeLoadStatus } from '../hooks/useLoadTicker'
import * as tickersApi from './tickers'

// Smoke test for the test harness itself (Vitest + jsdom), and a first
// real check on the load-status messaging (tasks.md 6.5) — each status
// must map to its own distinct, non-null message except "ok".
describe('describeLoadStatus', () => {
  it('returns null for a successful load', () => {
    expect(describeLoadStatus('ok', 'VNM')).toBeNull()
  })

  it('returns a distinct, retry-suggesting message for rate_limited', () => {
    expect(describeLoadStatus('rate_limited', 'VNM')).toMatch(/try again/i)
  })

  it('names the symbol for invalid_symbol', () => {
    expect(describeLoadStatus('invalid_symbol', 'NOTREAL')).toContain('NOTREAL')
  })

  it('returns a non-retry-suggesting message for no_data', () => {
    expect(describeLoadStatus('no_data', 'ABC')).toMatch(/unlikely to help/i)
  })

  it('gives each status a distinct message', () => {
    const messages = ['rate_limited', 'invalid_symbol', 'no_data'].map((status) =>
      describeLoadStatus(status, 'ABC'),
    )
    expect(new Set(messages).size).toBe(messages.length)
  })
})

describe('fetchTickerRange', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('calls GET /tickers/{ticker}/range and returns the body', async () => {
    const body = { ticker: 'TCB', as_of: '2026-10-06', status: 'ok', range_5s_pct: 3.2 }
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await tickersApi.fetchTickerRange('TCB')

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/tickers\/TCB\/range$/)
    expect(result).toEqual(body)
  })

  it('exports no fetcher for the retired prediction, insight or backtest endpoints', () => {
    expect(tickersApi.fetchTickerPrediction).toBeUndefined()
    expect(tickersApi.fetchTickerInsight).toBeUndefined()
    expect(tickersApi.backtestTicker).toBeUndefined()
  })
})
