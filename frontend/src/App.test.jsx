import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import * as tickersApi from './api/tickers'
import { INLINE_DISCLAIMER } from './lib/disclaimer'
import { resetFavoritesCache } from './hooks/useFavorites'
import { queryDefaults } from './lib/queryClient'
import { catalogEntry } from './test/railFixtures'
import { resetViewport, setViewport } from './test/viewport'

// Dashboard assembly: the Rail, the topbar search, the Stage and the Verdict panel all driven by the
// same `selectedTicker` state owned by App. These tests exercise the real composed tree — no props are
// injected into the child components — so they cover "one selection drives every ticker-scoped part",
// the load -> invalidate -> refetch flow, and the request budget the way a user would trigger them.
//
// A fresh QueryClient per render (not the app's `lib/queryClient` singleton) — same convention every
// other test file in this repo uses, so cache and retry state do not leak between files.
function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, ...queryDefaults }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

const TCB_ENTRY = catalogEntry('TCB', { in_training_set: true })
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

const selectRow = async (name) => userEvent.click(await screen.findByRole('button', { name }))
const verdictPanel = () => screen.getByRole('complementary', { name: 'Verdict' })

beforeEach(() => {
  vi.restoreAllMocks()
  // The 1440px layout: the Rail is a column, the search is a plain input.
  setViewport(1440)
})

afterEach(() => {
  resetFavoritesCache()
  resetViewport()
  document.documentElement.removeAttribute('data-theme')
  localStorage.clear()
})

describe('App (dashboard assembly)', () => {
  it('keeps the range block\'s shape with N/A placeholders, not an empty message, before any ticker is selected', async () => {
    spyOnEveryFetcher({ tickers: [] })

    renderApp()

    expect(await screen.findByText('Typical 5-session move')).toBeInTheDocument()
    expect(screen.getByText('N/A')).toBeInTheDocument()
    expect(screen.getByText('As of —')).toBeInTheDocument()
    // The Verdict panel and the Debate matrix each carry the disclaimer.
    expect(screen.getAllByText(INLINE_DISCLAIMER)).toHaveLength(2)
    expect(screen.getByText(/select a ticker to run debate analysis/i)).toBeInTheDocument()
  })

  it('names the selected ticker in the Stage h1, and says so when none is selected', async () => {
    spyOnEveryFetcher()

    renderApp()

    expect(await screen.findByRole('heading', { level: 1, name: 'No ticker selected' })).toBeInTheDocument()

    await selectRow(/^TCB/)

    expect(await screen.findByRole('heading', { level: 1, name: 'TCB' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'No ticker selected' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('selecting a Rail row replaces the placeholders with the band for that ticker and drives the chart, the Verdict panel and the matrix', async () => {
    spyOnEveryFetcher()

    renderApp()
    expect(await screen.findByText('N/A')).toBeInTheDocument()

    await selectRow(/^TCB/)

    expect(await screen.findByText('±3.20%')).toBeInTheDocument()
    expect(screen.queryByText('N/A')).not.toBeInTheDocument()
    expect(screen.queryByText(/select a ticker to see its chart/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyse TCB' })).toBeInTheDocument()
    expect(screen.getByText("Run Analyse to see each agent's Round 1 and Round 2 positions.")).toBeInTheDocument()
    expect(await screen.findByText(/^As of 2026-08-10/)).toBeInTheDocument()
  })

  it('searching and loading an unloaded ticker drives the chart and range without a manual refresh', async () => {
    const spies = spyOnEveryFetcher({
      tickers: [catalogEntry('VIB', { loaded: false, last_loaded_at: null, eligibility: null })],
    })

    renderApp()

    await userEvent.type(await screen.findByLabelText(/search ticker/i), 'VIB{Enter}')

    await waitFor(() => expect(spies.loadTicker).toHaveBeenCalledWith('VIB'))
    await waitFor(() => expect(spies.fetchTickerHistory).toHaveBeenCalledWith('VIB'))
    await waitFor(() => expect(spies.fetchTickerRange).toHaveBeenCalledWith('VIB'))
    expect(await screen.findByText('±3.20%')).toBeInTheDocument()
    expect(screen.getByLabelText(/search ticker/i)).toHaveValue('')
  })

  it('renders the Verdict panel and the Debate matrix with no environment variable set, and no retired panel exists', async () => {
    spyOnEveryFetcher()

    renderApp()
    await selectRow(/^TCB/)
    await screen.findByText('±3.20%')

    expect(screen.getByRole('button', { name: 'Analyse TCB' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Debate' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^confidence$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^advice$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /backtest this ticker/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument()
  })

  it('carries no leftover horizon-adjustment, advice-style, or disclaimer-visibility control anywhere on the page', async () => {
    spyOnEveryFetcher()

    renderApp()
    await selectRow(/^TCB/)
    await screen.findByText('±3.20%')

    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    // The only combobox-role control is the Rail's native sort select; the search input is a plain
    // input at this width (it becomes a combobox only below 768px).
    expect(screen.getAllByRole('combobox').map((el) => el.getAttribute('aria-label'))).toEqual(['Sort tickers'])
    expect(screen.getByLabelText(/search ticker/i)).not.toHaveAttribute('role')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByText(/horizon.*day/i)).not.toBeInTheDocument()
    expect(screen.getAllByText(INLINE_DISCLAIMER).length).toBeGreaterThan(0)
  })

  it('renders the hit-rate wording once, in the Verdict panel\'s range block, not in the chart, the header or the matrix', async () => {
    spyOnEveryFetcher()

    renderApp()
    await selectRow(/^TCB/)
    await screen.findByText('±3.20%')

    const hitRate = /36 of the last 48 five-session moves stayed inside it/
    expect(screen.getAllByText(hitRate)).toHaveLength(1)
    expect(within(verdictPanel()).getByText(hitRate)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: /price chart/i })).queryByText(hitRate)).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Debate' })).queryByText(hitRate)).not.toBeInTheDocument()
  })

  it('is one page: header, nav, main and aside landmarks, with the Rail in the nav and the verdict in the aside', async () => {
    spyOnEveryFetcher()

    renderApp()
    await selectRow(/^TCB/)

    expect(screen.getByRole('navigation', { name: 'Tickers' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toContainElement(verdictPanel())
    expect(screen.getByRole('banner')).toContainElement(screen.getByLabelText(/search ticker/i))
    expect(screen.getAllByRole('search')).toHaveLength(1)
  })

  it('has no width cap and no centred column on the shell (design: use the full viewport width)', () => {
    // jsdom doesn't compute real layout from stylesheets, so a rendered pixel-width assertion
    // wouldn't be meaningful here — read App.css's actual rule text instead.
    const css = readFileSync(join(process.cwd(), 'src/App.css'), 'utf-8')
    const cssWithoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
    const shellRule = cssWithoutComments.match(/\.app-shell\s*\{[^}]*\}/)[0]

    expect(shellRule).not.toMatch(/max-width/)
    expect(shellRule).not.toMatch(/margin:\s*0\s+auto/)
  })
})

describe('App favorites', () => {
  it('starring the selected ticker in the Stage header lists it in the Rail\'s Watchlist, and clearing the star takes it back', async () => {
    spyOnEveryFetcher({ tickers: [TCB_ENTRY, catalogEntry('VIB')] })
    renderApp()
    await selectRow(/^TCB/)
    const nav = screen.getByRole('navigation', { name: 'Tickers' })
    expect(within(nav).queryByRole('heading', { name: 'Watchlist' })).not.toBeInTheDocument()

    await userEvent.click(await screen.findByRole('button', { name: 'Favorite TCB' }))

    const watchlist = within(nav).getByRole('heading', { name: 'Watchlist' }).closest('section')
    expect(within(watchlist).getByRole('button', { name: /^TCB/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Favorite TCB' }))
    expect(within(nav).queryByRole('heading', { name: 'Watchlist' })).not.toBeInTheDocument()
  })
})

describe('App on a phone', () => {
  it('has no Rail, and the one search is the ticker picker', async () => {
    setViewport(390)
    spyOnEveryFetcher()

    renderApp()

    const search = await screen.findByLabelText(/search ticker/i)
    expect(search).toHaveAttribute('role', 'combobox')
    expect(screen.queryByRole('navigation', { name: 'Tickers' })).not.toBeInTheDocument()
  })

  it('selects a ticker from the picker and shows the range block before the chart, once', async () => {
    setViewport(390)
    spyOnEveryFetcher()

    renderApp()
    await userEvent.type(await screen.findByLabelText(/search ticker/i), 'tc')
    await userEvent.click(await screen.findByRole('option', { name: /^TCB/ }))

    const figure = await screen.findByText('±3.20%')
    expect(screen.getAllByText('±3.20%')).toHaveLength(1)
    const chart = screen.getByRole('region', { name: /price chart/i })
    expect(figure.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(verdictPanel()).queryByText('±3.20%')).not.toBeInTheDocument()
  })
})

describe('App request budget', () => {
  it('exports no fetcher for the retired endpoints', () => {
    const exported = Object.keys(tickersApi)

    expect(exported.filter((name) => /prediction|insight|backtest/i.test(name))).toEqual([])
  })

  it('makes exactly one request on mount: GET /tickers, whatever the catalog size', async () => {
    const tickers = Array.from({ length: 40 }, (_, i) => catalogEntry(`T${String(i).padStart(2, '0')}`))
    const spies = spyOnEveryFetcher({ tickers })

    renderApp()
    await screen.findByRole('button', { name: /^T39/ })
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(spies.fetchTickers).toHaveBeenCalledTimes(1)
    for (const [name, spy] of Object.entries(spies)) {
      if (name !== 'fetchTickers') expect(spy, name).not.toHaveBeenCalled()
    }
  })

  it('selecting a row adds one history and one range request for that ticker only', async () => {
    const spies = spyOnEveryFetcher({
      tickers: [TCB_ENTRY, catalogEntry('VIB'), catalogEntry('HPG')],
    })

    renderApp()
    await selectRow(/^VIB/)
    await screen.findByText('±3.20%')
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(spies.fetchTickers).toHaveBeenCalledTimes(1)
    expect(spies.fetchTickerHistory.mock.calls).toEqual([['VIB']])
    expect(spies.fetchTickerRange.mock.calls).toEqual([['VIB']])
    expect(spies.loadTicker).not.toHaveBeenCalled()
    expect(spies.runDebateAnalysis).not.toHaveBeenCalled()
  })

  it('sorting, filtering and switching the theme make no request', async () => {
    const spies = spyOnEveryFetcher({ tickers: [TCB_ENTRY, catalogEntry('VIB')] })
    renderApp()
    await selectRow(/^TCB/)
    await screen.findByText('±3.20%')
    const before = Object.fromEntries(Object.entries(spies).map(([name, spy]) => [name, spy.mock.calls.length]))

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sort tickers' }), 'Last loaded')
    await userEvent.type(screen.getByLabelText(/search ticker/i), 'vi')
    await userEvent.click(screen.getByRole('button', { name: 'Dark theme' }))
    await new Promise((resolve) => setTimeout(resolve, 50))

    for (const [name, spy] of Object.entries(spies)) expect(spy.mock.calls.length, name).toBe(before[name])
  })

  it('opening the drawer and typing into the search make no request', async () => {
    setViewport(900)
    const spies = spyOnEveryFetcher({ tickers: [TCB_ENTRY, catalogEntry('VIB')] })
    renderApp()
    await screen.findByRole('button', { name: /^TCB/, hidden: true })

    await userEvent.click(screen.getByRole('button', { name: 'Tickers' }))
    await userEvent.type(screen.getByLabelText(/search ticker/i), 'v')
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(spies.fetchTickers).toHaveBeenCalledTimes(1)
    for (const [name, spy] of Object.entries(spies)) {
      if (name !== 'fetchTickers') expect(spy, name).not.toHaveBeenCalled()
    }
  })

  it('crossing a layout breakpoint remounts parts of the page and still makes no request', async () => {
    const viewport = setViewport(1440)
    const spies = spyOnEveryFetcher({ tickers: [TCB_ENTRY] })
    renderApp()
    await selectRow(/^TCB/)
    await screen.findByText('±3.20%')
    const before = Object.fromEntries(Object.entries(spies).map(([name, spy]) => [name, spy.mock.calls.length]))

    for (const width of [390, 900, 1300, 1440]) {
      act(() => viewport.setWidth(width))
      await new Promise((resolve) => setTimeout(resolve, 20))
    }
    await screen.findByText('±3.20%')

    for (const [name, spy] of Object.entries(spies)) expect(spy.mock.calls.length, name).toBe(before[name])
  })

  it('a successful Refresh refetches the catalog and, for the selected ticker only, its history and range', async () => {
    const spies = spyOnEveryFetcher({ tickers: [TCB_ENTRY, catalogEntry('VIB')] })
    spies.loadTicker.mockImplementation(async (ticker) => ({ ticker, status: 'ok', rows_loaded: 300 }))
    renderApp()
    await selectRow(/^TCB/)
    await screen.findByText('±3.20%')

    await userEvent.click(screen.getByRole('button', { name: 'Refresh VIB' })) // not the selected ticker
    await waitFor(() => expect(spies.fetchTickers).toHaveBeenCalledTimes(2))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(spies.fetchTickerHistory.mock.calls).toEqual([['TCB']])
    expect(spies.fetchTickerRange.mock.calls).toEqual([['TCB']])

    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))
    await waitFor(() => expect(spies.fetchTickerHistory.mock.calls).toEqual([['TCB'], ['TCB']]))
    await waitFor(() => expect(spies.fetchTickerRange.mock.calls).toEqual([['TCB'], ['TCB']]))
    expect(spies.fetchTickers).toHaveBeenCalledTimes(3)
  })

  it('no flow ever requests /prediction, /insight or /backtest', async () => {
    const spies = spyOnEveryFetcher()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderApp()
    await selectRow(/^TCB/)
    await userEvent.type(screen.getByLabelText(/search ticker/i), 'VIB{Enter}')
    await userEvent.click(screen.getByRole('button', { name: 'Refresh TCB' }))
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(spies.loadTicker).toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled() // every request goes through the stubbed fetchers
  })
})
