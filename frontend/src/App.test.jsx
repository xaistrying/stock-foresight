import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import * as tickersApi from './api/tickers'

// Dashboard assembly (tasks.md section 11): TickerPanel, ChartPanel,
// PredictionDisplay, and AIInsightPanel all driven by the same
// `selectedTicker` state owned by App. These tests exercise the real
// composed tree — no props are injected directly into the child panels —
// so they cover 11.1 (one selection drives all four panels) and 11.2 (the
// load -> auto-predict -> invalidate -> refetch flow, end to end) the way
// a user would actually trigger them.
//
// A fresh QueryClient per render (not the app's `lib/queryClient` singleton)
// — same convention every other test file in this repo uses. Reusing the
// singleton across test files leaked cache/retry state between them when
// run in the same suite (observed as TickerPanel's tests hanging on the
// loading skeleton when run alongside this file).
function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('App (dashboard assembly)', () => {
  it('selecting an already-loaded chip drives the chart, prediction, and AI insight panel for that ticker', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-08-10', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: 0.02,
    })
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.75,
      confidence_basis: "Hit-rate over the ticker's most recent 60 backtested predictions.",
      sentiment_proxy: 'bullish',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'up',
      note: null,
    })

    renderApp()

    const chip = await screen.findByRole('button', { name: /TCB/ })
    await userEvent.click(chip)

    // Prediction display for TCB.
    expect(await screen.findByText(/\+2\.02%/)).toBeInTheDocument()
    // AI insight panel for the same ticker.
    expect(await screen.findByText('75%')).toBeInTheDocument()
    expect(screen.getByText('Technical Signal')).toBeInTheDocument()
    expect(screen.getByText('Signal: up')).toBeInTheDocument()
    // Chart panel dropped its "select a ticker" empty state.
    expect(screen.queryByText(/select a ticker to see its chart/i)).not.toBeInTheDocument()
  })

  it('clicking an unloaded chip loads it, then auto-predicts without a manual refresh or separate action', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', loaded: false, features_computed: null, last_loaded_at: null }],
    })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'ok', rows_loaded: 300 })
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'VIB',
      rows: [{ date: '2026-08-10', open: 20, high: 21, low: 19, close: 20.5, volume: 200 }],
    })
    const predictionSpy = vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'VIB',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: -0.01,
    })
    const insightSpy = vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'VIB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: null,
      confidence_basis: 'No backtested predictions for this ticker yet.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderApp()

    const chip = await screen.findByRole('button', { name: /VIB/ })
    await userEvent.click(chip)

    // No separate user action requests the prediction/insight — clicking
    // the unloaded chip alone is enough for both to fetch and render.
    await waitFor(() => expect(predictionSpy).toHaveBeenCalledWith('VIB'))
    await waitFor(() => expect(insightSpy).toHaveBeenCalledWith('VIB'))
    expect(await screen.findByText('N/A')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /backtest this ticker/i })).toBeInTheDocument()
  })

  it('searching a ticker not yet in the DB loads it, then drives chart/prediction/insight the same way a chip would', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [] })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'FPT',
      rows: [{ date: '2026-08-10', open: 30, high: 31, low: 29, close: 30.5, volume: 300 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'FPT',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: 0.0,
    })
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'FPT',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: null,
      confidence_basis: 'No backtested predictions for this ticker yet.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderApp()

    const input = await screen.findByLabelText(/search ticker/i)
    await userEvent.type(input, 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    expect(await screen.findByRole('button', { name: /FPT/ })).toBeInTheDocument()
    expect(await screen.findByText(/\+0\.00%/)).toBeInTheDocument()
    expect(await screen.findByText('Technical Signal')).toBeInTheDocument()
  })

  it('carries no leftover horizon-adjustment, advice-style, or disclaimer-visibility control anywhere on the page', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-08-10', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: 0.02,
    })
    vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      confidence_score: 0.75,
      confidence_basis: 'Hit-rate over recent predictions.',
      sentiment_proxy: 'neutral',
      sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
      advice_text: 'HOLD',
      note: null,
    })

    renderApp()
    const chip = await screen.findByRole('button', { name: /TCB/ })
    await userEvent.click(chip)
    await screen.findByText('Technical Signal')

    // design.md Decision 9: horizonDays slider, adviceStyle dropdown, and a
    // showDisclaimer toggle were all reviewed and dropped, not relocated.
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByText(/horizon.*day/i)).not.toBeInTheDocument()
  })

  it('fills the viewport width — .app-shell no longer caps width to a centered column (design.md Decision 14)', () => {
    // jsdom doesn't compute real layout from stylesheets, so a rendered
    // pixel-width assertion wouldn't be meaningful here — read App.css's
    // actual rule text instead, per task 11.4's own suggested check.
    const css = readFileSync(join(process.cwd(), 'src/App.css'), 'utf-8')
    const cssWithoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
    const appShellRule = cssWithoutComments.match(/\.app-shell\s*\{[^}]*\}/)[0]

    expect(appShellRule).not.toMatch(/max-width/)
    expect(appShellRule).not.toMatch(/margin:\s*0\s+auto/)
  })
})
