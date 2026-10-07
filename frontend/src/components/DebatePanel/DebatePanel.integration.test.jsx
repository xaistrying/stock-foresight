import { useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { DebatePanel } from './DebatePanel'

// The real hooks, the real query cache, and a stubbed API: what the panel and its hooks do
// together when the user switches tickers. DebatePanel.test.jsx mocks the hooks, so it cannot
// show this. The harness keys the panel by ticker exactly as App does.

const position = (agent, stance) => ({
  agent_id: agent, stance, reasoning: [`${agent} reasoning`],
  range_5s_pct: null, sigma_daily_pct: null, range_coverage: null, degraded_reason: null,
})
const RESULT = {
  ticker: 'VCB', as_of: '2026-10-07', data_as_of: '2026-10-07', data_age_sessions: 0,
  verdict: 'BUY_SIGNAL', agreement_level: 'majority',
  eligibility: { eligible: true, reasons: [] }, agents_degraded: [],
  round1: { technical: position('technical', 'bull'), news: position('news', 'bull'), macro: position('macro', 'neutral') },
  round2: { technical: position('technical', 'bull'), news: position('news', 'bull'), macro: position('macro', 'neutral') },
  synthesis: { verdict: 'BUY_SIGNAL', agreement_level: 'majority', key_tension: 'A tension.', reasoning: 'A summary.' },
  range_5s_pct: null, sigma_daily_pct: null, range_coverage: null, duration_ms: 1000,
  report_saved: true, report_file: '2026-10-07_VCB.md',
}

function Harness() {
  const [ticker, setTicker] = useState('VCB')
  return (
    <>
      <button type="button" onClick={() => setTicker((t) => (t === 'VCB' ? 'FPT' : 'VCB'))}>switch</button>
      <DebatePanel key={ticker} ticker={ticker} />
    </>
  )
}

function renderHarness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  )
}

const switchTicker = () => fireEvent.click(screen.getByRole('button', { name: 'switch' }))

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DebatePanel with its real hooks', () => {
  function stubApi() {
    let finish
    let fail
    const run = vi.spyOn(tickersApi, 'runDebateAnalysis').mockImplementation(
      () => new Promise((resolve, reject) => {
        finish = () => resolve(RESULT)
        fail = (error) => reject(error)
      }),
    )
    vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue({
      ticker: 'VCB', running: true, stage: 'round2', elapsed_ms: 1000,
    })
    return { run, finish: () => finish(), fail: (error) => fail(error) }
  }

  it('runs, shows the server stage and the kept result with its time', async () => {
    const api = stubApi()
    renderHarness()

    fireEvent.click(screen.getByRole('button', { name: /analyse vcb/i }))
    expect(await screen.findByText('Comparing positions…')).toBeInTheDocument()
    expect(screen.getByText(/^\d+ s$/)).toBeInTheDocument() // not "0 s": a slow runner may be past a second

    await act(async () => api.finish())

    expect(await screen.findByText('Bullish lean')).toBeInTheDocument()
    expect(screen.getByText(/^Analysed \d\d:\d\d$/)).toBeInTheDocument()
  })

  it('a run survives a ticker switch, and its result is there when the user comes back, with no new request', async () => {
    const api = stubApi()
    renderHarness()
    fireEvent.click(screen.getByRole('button', { name: /analyse vcb/i }))
    await screen.findByText('Comparing positions…')

    switchTicker() // FPT, never analysed this session
    expect(screen.getByRole('button', { name: /analyse fpt/i })).toBeInTheDocument()
    expect(screen.queryByText('Comparing positions…')).not.toBeInTheDocument()

    await act(async () => api.finish()) // VCB finishes while FPT is on screen
    expect(screen.queryByText('Bullish lean')).not.toBeInTheDocument()

    switchTicker() // back to VCB
    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(screen.getByText(/^Analysed \d\d:\d\d$/)).toBeInTheDocument()
    expect(api.run).toHaveBeenCalledTimes(1)
  })

  it('returning to a ticker whose run is still going shows the running state', async () => {
    const api = stubApi()
    renderHarness()
    fireEvent.click(screen.getByRole('button', { name: /analyse vcb/i }))
    await screen.findByText('Comparing positions…')

    switchTicker()
    switchTicker()

    expect(await screen.findByText('Comparing positions…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /analyse vcb/i })).not.toBeInTheDocument()
    await act(async () => api.finish())
    expect(api.run).toHaveBeenCalledTimes(1)
  })

  it('a failed re-run keeps the earlier result, with the reason above it', async () => {
    const api = stubApi()
    renderHarness()
    fireEvent.click(screen.getByRole('button', { name: /analyse vcb/i }))
    await screen.findByText('Comparing positions…')
    await act(async () => api.finish())
    await screen.findByText('Bullish lean')

    fireEvent.click(screen.getByRole('button', { name: /re-analyse vcb/i }))
    await screen.findByText('Comparing positions…')
    await act(async () => api.fail(new ApiError('Another analysis is already running; try again shortly.', {
      status: 429, body: { code: 'debate_busy' },
    })))

    expect(await screen.findByRole('alert')).toHaveTextContent('Another analysis is already running; try again shortly.')
    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
  })
})
