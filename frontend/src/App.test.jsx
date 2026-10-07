import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import * as tickersApi from './api/tickers'
import { INLINE_DISCLAIMER } from './lib/disclaimer'

// Dashboard assembly: TickerPanel, ChartPanel, RangeDisplay and DebatePanel all driven by the
// same `selectedTicker` state owned by App. These tests exercise the real composed tree — no
// props are injected into the child panels — so they cover "one selection drives every
// ticker-scoped panel", the load -> invalidate -> refetch flow, and the request budget the way
// a user would trigger them.
//
// A fresh QueryClient per render (not the app's `lib/queryClient` singleton) — same convention
// every other test file in this repo uses, so cache and retry state do not leak between files.
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

const TCB_ENTRY = { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }
const TCB_HISTORY = {
  ticker: 'TCB',
  rows: [{ date: '2026-08-10', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
}
const rangeFor = (ticker, overrides = {}) => ({
  ticker,
  as_of: '2026-08-10',
  status: 'ok',
  reasons: [],
  sigma_daily_pct: 1.37,
  range_5s_pct: 3.2,
  range_k: 1.1,
  range_coverage: 0.68,
  range_hit_rate: { rate: 0.75, n: 48 },
  ...overrides,
})

// Every function api/tickers.js exports as a fetcher, spied so a test can count calls.
function spyOnEveryFetcher({ tickers = [TCB_ENTRY] } = {}) {
  return {
    fetchTickers: vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers }),
    fetchTickerHistory: vi
      .spyOn(tickersApi, 'fetchTickerHistory')
      .mockImplementation(async (ticker) => ({ ...TCB_HISTORY, ticker })),
    fetchTickerRange: vi.spyOn(tickersApi, 'fetchTickerRange').mockImplementation(async (ticker) => rangeFor(ticker)),
    loadTicker: vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'ok', rows_loaded: 300 }),
    runDebateAnalysis: vi.spyOn(tickersApi, 'runDebateAnalysis'),
    getDebateProgress: vi.spyOn(tickersApi, 'getDebateProgress'),
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('App (dashboard assembly)', () => {
  it('shows N/A placeholders in the range card (not an empty message) before any ticker is selected', async () => {
    spyOnEveryFetcher({ tickers: [] })

    renderApp()

    expect(await screen.findByRole('heading', { name: /5-session range/i })).toBeInTheDocument()
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    expect(screen.getByText('As of —')).toBeInTheDocument()
    // The disclaimer renders unconditionally, in the range card and in the debate panel.
    expect(screen.getAllByText(INLINE_DISCLAIMER)).toHaveLength(2)
    expect(screen.getByText(/select a ticker to run debate analysis/i)).toBeInTheDocument()
  })

  it('names the selected ticker in a heading above the panels, and says so when none is selected', async () => {
    spyOnEveryFetcher()

    renderApp()

    expect(await screen.findByRole('heading', { name: 'No ticker selected' })).toBeInTheDocument()

    await userEvent.click(await screen.findByRole('button', { name: /^TCB/ }))

    expect(await screen.findByRole('heading', { name: 'TCB' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'No ticker selected' })).not.toBeInTheDocument()
  })

  it('selecting a chip replaces the placeholders with the range for that ticker and drives the chart and debate panel', async () => {
    spyOnEveryFetcher()

    renderApp()
    expect(await screen.findByRole('heading', { name: /5-session range/i })).toBeInTheDocument()
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)

    await userEvent.click(await screen.findByRole('button', { name: /^TCB/ }))

    expect(await screen.findByText('±3.2%')).toBeInTheDocument()
    expect(screen.queryByText('N/A')).not.toBeInTheDocument()
    expect(screen.queryByText(/select a ticker to see its chart/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyse TCB' })).toBeInTheDocument()
  })

  it('searching and loading an unloaded ticker drives the chart and range without a manual refresh', async () => {
    const spies = spyOnEveryFetcher({
      tickers: [{ ticker: 'VIB', in_training_set: true, loaded: false, features_computed: null, last_loaded_at: null }],
    })

    renderApp()

    await userEvent.type(await screen.findByLabelText(/search ticker/i), 'VIB')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    await waitFor(() => expect(spies.loadTicker).toHaveBeenCalledWith('VIB'))
    await waitFor(() => expect(spies.fetchTickerHistory).toHaveBeenCalledWith('VIB'))
    await waitFor(() => expect(spies.fetchTickerRange).toHaveBeenCalledWith('VIB'))
    expect(await screen.findByText('±3.2%')).toBeInTheDocument()
  })

  it('renders the debate panel with no environment variable set, and no retired panel exists', async () => {
    vi.stubEnv('VITE_DEBATE_PANEL_ENABLED', '')
    spyOnEveryFetcher()

    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: /^TCB/ }))
    await screen.findByText('±3.2%')

    expect(screen.getByRole('button', { name: 'Analyse TCB' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^confidence$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^advice$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /backtest this ticker/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument()
  })

  it('carries no leftover horizon-adjustment, advice-style, or disclaimer-visibility control anywhere on the page', async () => {
    spyOnEveryFetcher()

    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: /^TCB/ }))
    await screen.findByText('±3.2%')

    // design.md Decision 9 of the original dashboard: horizonDays slider, adviceStyle dropdown
    // and a showDisclaimer toggle were reviewed and dropped, not relocated.
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByText(/horizon.*day/i)).not.toBeInTheDocument()
    expect(screen.getAllByText(INLINE_DISCLAIMER).length).toBeGreaterThan(0)
  })

  it('renders the hit-rate wording in the range card only, not in the chart panel or the debate panel', async () => {
    spyOnEveryFetcher()

    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: /^TCB/ }))
    await screen.findByText('±3.2%')

    const hitRate = /36 of the last 48 five-session moves/
    expect(screen.getAllByText(hitRate)).toHaveLength(1)
    const rangeCard = screen.getByText('±3.2%').closest('section')
    expect(within(rangeCard).getByText(hitRate)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: /price chart/i })).queryByText(hitRate)).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: /debate analysis/i })).queryByText(hitRate)).not.toBeInTheDocument()
  })

  it('fills the viewport width — .app-shell no longer caps width to a centered column (design.md Decision 14)', () => {
    // jsdom doesn't compute real layout from stylesheets, so a rendered pixel-width assertion
    // wouldn't be meaningful here — read App.css's actual rule text instead.
    const css = readFileSync(join(process.cwd(), 'src/App.css'), 'utf-8')
    const cssWithoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
    const appShellRule = cssWithoutComments.match(/\.app-shell\s*\{[^}]*\}/)[0]

    expect(appShellRule).not.toMatch(/max-width/)
    expect(appShellRule).not.toMatch(/margin:\s*0\s+auto/)
  })
})

describe('App request budget', () => {
  it('exports no fetcher for the retired endpoints', () => {
    const exported = Object.keys(tickersApi)

    expect(exported.filter((name) => /prediction|insight|backtest/i.test(name))).toEqual([])
  })

  it('makes exactly one request on mount: GET /tickers, whatever the catalog size', async () => {
    const tickers = Array.from({ length: 40 }, (_, i) => ({
      ticker: `T${String(i).padStart(2, '0')}`,
      in_training_set: false,
      loaded: true,
      features_computed: true,
      last_loaded_at: '2026-08-10',
    }))
    const spies = spyOnEveryFetcher({ tickers })

    renderApp()
    await screen.findByRole('button', { name: /^T39/ })
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(spies.fetchTickers).toHaveBeenCalledTimes(1)
    for (const [name, spy] of Object.entries(spies)) {
      if (name !== 'fetchTickers') expect(spy, name).not.toHaveBeenCalled()
    }
  })

  it('selecting a chip adds one history and one range request for that ticker only', async () => {
    const spies = spyOnEveryFetcher({
      tickers: [TCB_ENTRY, { ...TCB_ENTRY, ticker: 'VIB' }, { ...TCB_ENTRY, ticker: 'HPG' }],
    })

    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: /^VIB/ }))
    await screen.findByText('±3.2%')
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(spies.fetchTickers).toHaveBeenCalledTimes(1)
    expect(spies.fetchTickerHistory.mock.calls).toEqual([['VIB']])
    expect(spies.fetchTickerRange.mock.calls).toEqual([['VIB']])
    expect(spies.loadTicker).not.toHaveBeenCalled()
    expect(spies.runDebateAnalysis).not.toHaveBeenCalled()
  })
})
