import { useState } from 'react'
import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VerdictPanel } from './VerdictPanel'
import { DebateMatrix } from '../DebateMatrix/DebateMatrix'
import { useDebateAnalysis } from '../../hooks/useDebateAnalysis'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { catalogEntry, renderWithQuery } from '../../test/railFixtures'
import { populated } from '../../test/debateFixtures'

// The real hooks, the real query cache and a stubbed API: what the Verdict panel and the Debate
// matrix do together when the user runs an analysis and switches tickers. The panel and the matrix
// both read ONE useDebateAnalysis call, made here as the workspace makes it.
const RESULT = populated({ ticker: 'VCB', data_as_of: '2026-10-07', data_age_sessions: 0, report_saved: true, report_file: '2026-10-07_VCB.md' })

function Workspace({ ticker }) {
  const analysis = useDebateAnalysis(ticker)
  return (
    <>
      <VerdictPanel ticker={ticker} analysis={analysis} showRange={false} />
      <DebateMatrix key={ticker} ticker={ticker} analysis={analysis} layoutMode="wide" />
    </>
  )
}

function Harness() {
  const [ticker, setTicker] = useState('VCB')
  return (
    <>
      <button type="button" onClick={() => setTicker((t) => (t === 'VCB' ? 'FPT' : 'VCB'))}>switch</button>
      <Workspace ticker={ticker} />
    </>
  )
}

const switchTicker = () => fireEvent.click(screen.getByRole('button', { name: 'switch' }))
const panel = () => screen.getByRole('complementary', { name: 'Verdict' })
const matrix = () => screen.getByRole('region', { name: 'Debate' })

function stubApi() {
  let finish
  let fail
  const run = vi.spyOn(tickersApi, 'runDebateAnalysis').mockImplementation(
    () => new Promise((resolve, reject) => {
      finish = () => resolve(RESULT)
      fail = (error) => reject(error)
    }),
  )
  vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue({ ticker: 'VCB', running: true, stage: 'round2', elapsed_ms: 1000 })
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [catalogEntry('VCB'), catalogEntry('FPT')] })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockImplementation(async (ticker) => ({
    ticker, rows: [{ date: '2026-10-07', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
  }))
  vi.spyOn(tickersApi, 'fetchTickerRange').mockImplementation(async (ticker) => ({
    ticker, as_of: '2026-10-07', status: 'ok', reasons: [], sigma_daily_pct: 1.4, range_5s_pct: 4.12,
    range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 },
  }))
  return { run, finish: () => finish(), fail: (error) => fail(error) }
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Verdict panel and Debate matrix with their real hooks', () => {
  it('runs, shows the server stage, then the kept result in both places from one request', async () => {
    const api = stubApi()
    renderWithQuery(<Harness />)

    fireEvent.click(await screen.findByRole('button', { name: /analyse vcb/i }))
    expect(await screen.findByText('Comparing positions…')).toBeInTheDocument()
    expect(screen.getByText(/^\d+ s$/)).toBeInTheDocument() // not "0 s": a slow runner may be past a second
    expect(matrix().querySelectorAll('.agent-card--skeleton')).toHaveLength(6)

    await act(async () => api.finish())

    expect(await within(panel()).findByText('Bullish lean')).toBeInTheDocument()
    expect(within(panel()).getByText(/^Analysed \d\d:\d\d$/)).toBeInTheDocument()
    expect(within(matrix()).getAllByRole('article')).toHaveLength(6)
    expect(within(matrix()).getByText('RSI at 62 is bullish')).toBeInTheDocument()
    expect(api.run).toHaveBeenCalledTimes(1)
  })

  it('a run survives a ticker switch, and its result is there when the user comes back, with no new request', async () => {
    const api = stubApi()
    renderWithQuery(<Harness />)
    fireEvent.click(await screen.findByRole('button', { name: /analyse vcb/i }))
    await screen.findByText('Comparing positions…')

    switchTicker() // FPT, never analysed this session
    expect(await screen.findByRole('button', { name: /analyse fpt/i })).toBeInTheDocument()
    expect(screen.queryByText('Comparing positions…')).not.toBeInTheDocument()
    expect(within(matrix()).queryByRole('article')).not.toBeInTheDocument()

    await act(async () => api.finish()) // VCB finishes while FPT is on screen
    expect(screen.queryByText('Bullish lean')).not.toBeInTheDocument()

    switchTicker() // back to VCB
    expect(await within(panel()).findByText('Bullish lean')).toBeInTheDocument()
    expect(within(panel()).getByText(/^Analysed \d\d:\d\d$/)).toBeInTheDocument()
    expect(within(matrix()).getAllByRole('article')).toHaveLength(6)
    expect(api.run).toHaveBeenCalledTimes(1)
  })

  it('returning to a ticker whose run is still going shows the running state in both places', async () => {
    const api = stubApi()
    renderWithQuery(<Harness />)
    fireEvent.click(await screen.findByRole('button', { name: /analyse vcb/i }))
    await screen.findByText('Comparing positions…')

    switchTicker()
    switchTicker()

    expect(await screen.findByText('Comparing positions…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /analyse vcb/i })).not.toBeInTheDocument()
    expect(matrix().querySelectorAll('.agent-card--skeleton')).toHaveLength(6)
    await act(async () => api.finish())
    expect(api.run).toHaveBeenCalledTimes(1)
  })

  it('a failed re-run keeps the earlier result in both places, with the reason above it in the panel', async () => {
    const api = stubApi()
    renderWithQuery(<Harness />)
    fireEvent.click(await screen.findByRole('button', { name: /analyse vcb/i }))
    await screen.findByText('Comparing positions…')
    await act(async () => api.finish())
    await within(panel()).findByText('Bullish lean')

    fireEvent.click(screen.getByRole('button', { name: /re-analyse vcb/i }))
    await screen.findByText('Comparing positions…')
    await act(async () => api.fail(new ApiError('Another analysis is already running; try again shortly.', {
      status: 429, body: { code: 'debate_busy' },
    })))

    expect(await within(panel()).findByRole('alert')).toHaveTextContent('Another analysis is already running; try again shortly.')
    expect(within(panel()).getByText('Bullish lean')).toBeInTheDocument()
    expect(within(matrix()).getAllByRole('article')).toHaveLength(6)
  })
})
