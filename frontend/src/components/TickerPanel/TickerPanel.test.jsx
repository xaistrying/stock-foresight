import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TickerPanel } from './TickerPanel'
import * as tickersApi from '../../api/tickers'

// Mirrors GET /tickers/{ticker}/prediction and /history enough for the
// freshness computation (useTickerFreshness) to resolve deterministically
// in tests, without a real backend. Also mocks /insight — TickerChip now
// prefetches it the same way (adjacent fix, see useTickerInsight.js) — so
// existing tests don't hit the network for a query they don't care about.
function mockFreshData() {
  vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
    ticker: 'TCB',
    as_of: '2026-08-10',
    status: 'ok',
    predicted_log_return: 0.01,
  })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
    ticker: 'TCB',
    rows: [{ date: '2026-08-10', open: 1, high: 1, low: 1, close: 1, volume: 1 }],
  })
  vi.spyOn(tickersApi, 'fetchTickerInsight').mockResolvedValue({
    ticker: 'TCB',
    confidence_score: 0.55,
    confidence_basis: '60-prediction backtested hit-rate.',
    sentiment_proxy: 'bullish',
    sentiment_inputs: ['RSI', 'MACD', 'Ichimoku position'],
    advice_text: 'HOLD',
  })
}

function renderPanel(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const defaultProps = { selectedTicker: null, onSelectTicker: vi.fn() }
  const merged = { ...defaultProps, ...props }
  render(
    <QueryClientProvider client={queryClient}>
      <TickerPanel {...merged} />
    </QueryClientProvider>,
  )
  return merged
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('TickerPanel', () => {
  it('renders one chip per loaded ticker from GET /tickers', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-11' },
      ],
    })
    mockFreshData()

    renderPanel()

    expect(await screen.findByRole('button', { name: /^TCB/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^VIB/ })).toBeInTheDocument()
  })

  it('shows only loaded tickers in the Watchlist when the catalog is universe-sized', async () => {
    // The Watchlist now shows loaded:true tickers only. Unloaded universe
    // symbols (loaded:false) are reachable via search, not shown as chips.
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        ...Array.from({ length: 300 }, (_, i) => ({
          ticker: `S${String(i).padStart(3, '0')}`,
          in_training_set: false,
          loaded: false,
          features_computed: null,
          last_loaded_at: null,
        })),
      ],
    })
    mockFreshData()

    renderPanel()

    // Only TCB (loaded:true) should appear as a chip; the 300 unloaded
    // universe symbols should not.
    expect(await screen.findByRole('button', { name: /^TCB/ })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^[A-Z]{2,}[0-9]*/ })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /^S000/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^S299/ })).not.toBeInTheDocument()
  })

  it('unloaded tickers do not appear as Watchlist chips', async () => {
    // Unloaded tickers are reachable only via search, not as chips.
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', in_training_set: true, loaded: false, features_computed: null, last_loaded_at: null }],
    })

    renderPanel()

    // Wait for the panel to settle (no chips should appear)
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByRole('button', { name: /VIB/ })).not.toBeInTheDocument()
  })

  it('clicking an already-loaded chip selects it directly, without a /load call', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    const loadSpy = vi.spyOn(tickersApi, 'loadTicker')

    const { onSelectTicker } = renderPanel()
    const chip = await screen.findByRole('button', { name: /^TCB/ })
    await userEvent.click(chip)

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
    expect(loadSpy).not.toHaveBeenCalled()
  })

  it('searching and loading a new ticker triggers /load and selects on success', async () => {
    // Unloaded tickers are loaded via search, not via chip click.
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'ok', rows_loaded: 300 })

    const { onSelectTicker } = renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'VIB')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('VIB'))
  })

  it('shows a distinct message per load-failure status, not a generic one', async () => {
    // Load failures are surfaced via the search flow.
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'rate_limited' })

    const { onSelectTicker } = renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'VIB')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    expect(await screen.findByText(/try again in a moment/i)).toBeInTheDocument()
    expect(onSelectTicker).not.toHaveBeenCalled()
  })

  it('search resolves an already-known ticker directly, without a new /load call', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    const loadSpy = vi.spyOn(tickersApi, 'loadTicker')

    const { onSelectTicker } = renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'TCB')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
    expect(loadSpy).not.toHaveBeenCalled()
  })

  it('searching a symbol the catalog lists but has not loaded triggers /load, then selects it', async () => {
    // Unloaded catalog entries have no chip, so search is the only way to
    // load them — it must not treat them as already-known and skip /load.
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', in_training_set: true, loaded: false, features_computed: null, last_loaded_at: null }],
    })
    const loadSpy = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'ok', rows_loaded: 300 })

    const { onSelectTicker } = renderPanel()
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'VIB')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    await waitFor(() => expect(loadSpy).toHaveBeenCalledWith('VIB'))
    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('VIB'))
  })

  it('searching a new ticker triggers /load and adds it to the selectable list on success', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [] })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })

    const { onSelectTicker } = renderPanel()
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('FPT'))
    expect(await screen.findByRole('button', { name: /^FPT/ })).toBeInTheDocument()
  })

  it('searching an unrecognized symbol shows a symbol-specific message, not a generic one', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [] })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'NOTREAL', status: 'invalid_symbol' })

    renderPanel()
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'NOTREAL')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    expect(await screen.findByText(/"NOTREAL" isn't a recognized ticker symbol/i)).toBeInTheDocument()
  })

  it('searching a well-formed symbol with no data shows a non-retry-suggesting message', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [] })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'ABC', status: 'no_data' })

    renderPanel()
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'ABC')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    expect(await screen.findByText(/unlikely to help/i)).toBeInTheDocument()
  })

  it('shows a freshness dot with an accessible label instead of visible "Fresh" text', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()

    renderPanel()

    const chip = await screen.findByRole('button', { name: /^TCB/ })
    await waitFor(() => {
      expect(chip.querySelector('.ticker-chip__dot')).toHaveAttribute('data-freshness', 'fresh')
    })
    // No bare "Fresh" text label inside the chip anymore...
    expect(chip).not.toHaveTextContent('Fresh')
    // ...but the dot itself carries the same meaning accessibly (WCAG
    // color-not-only: color alone must not be the only signal).
    const dot = chip.querySelector('.ticker-chip__dot')
    expect(dot).toHaveAccessibleName(/fresh/i)
  })

  it('renders a freshness legend explaining the dot colors, without duplicating the accessibility tree', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    expect(screen.getByText('Fresh')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('Loading')).toBeInTheDocument()
  })

  it('marks the selected ticker distinctly from unselected ones', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
      ],
    })
    mockFreshData()

    renderPanel({ selectedTicker: 'TCB' })

    const tcbChip = await screen.findByRole('button', { name: /^TCB/ })
    const vibChip = screen.getByRole('button', { name: /^VIB/ })
    expect(tcbChip).toHaveAttribute('aria-pressed', 'true')
    expect(vibChip).toHaveAttribute('aria-pressed', 'false')
  })
})

// The Watchlist is a fixed-height scroll region (ticker-panel.css), so a
// ticker selected via search could otherwise sit in an out-of-view row. The
// selected chip scrolls itself into view. jsdom doesn't implement
// scrollIntoView, so each test installs a spy and removes it afterwards.
describe('TickerPanel selected-chip visibility', () => {
  afterEach(() => {
    delete HTMLElement.prototype.scrollIntoView
  })

  function installScrollSpy() {
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollIntoView,
    })
    return scrollIntoView
  }

  const twoTickers = {
    tickers: [
      { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
      { ticker: 'VIB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
    ],
  }

  it('scrolls the selected chip into view, nearest edge only', async () => {
    const scrollIntoView = installScrollSpy()
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue(twoTickers)
    mockFreshData()

    renderPanel({ selectedTicker: 'VIB' })
    await screen.findByRole('button', { name: /^VIB/ })

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
    // Called on the selected chip's own container, not on the other one.
    const target = scrollIntoView.mock.contexts[0]
    expect(within(target).getByRole('button', { name: /^VIB/ })).toBeInTheDocument()
  })

  it('does not scroll for a Searched-list row, only for Watchlist chips', async () => {
    // A searched-in ticker also becomes a Watchlist chip once /tickers
    // refetches it as loaded; only the Watchlist is a scroll region, and
    // scrollIntoView would otherwise also scroll the page for the row.
    const scrollIntoView = installScrollSpy()
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })

    // FPT is selected from the start; it only exists as a Searched row
    // (the catalog mock never lists it) once the search-load succeeds.
    renderPanel({ selectedTicker: 'FPT' })
    await screen.findByRole('button', { name: /^TCB/ })
    await userEvent.type(screen.getByLabelText(/search ticker/i), 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    const searched = await screen.findByRole('group', { name: 'Searched tickers' })
    expect(within(searched).getByRole('button', { name: /^FPT/ })).toBeInTheDocument()
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('does not scroll anything when no ticker is selected', async () => {
    const scrollIntoView = installScrollSpy()
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue(twoTickers)
    mockFreshData()

    renderPanel({ selectedTicker: null })
    await screen.findByRole('button', { name: /^VIB/ })

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})

// redesign-dashboard-visual-look: the Watchlist and every searched-in
// ticker beyond it render as two separately-labeled groups. The search
// input live-filters BOTH: the Watchlist is now every loaded ticker (208 in
// the real universe), so a filter that left it untouched would make the
// input useless as navigation. This supersedes the dashboard-ui spec's
// "Filter narrows the searched-in list only" / "Fixed Watchlist remains
// visible regardless of filter input" scenarios, which assumed a fixed
// 9-ticker Watchlist.
describe('TickerPanel Watchlist / searched-tickers split', () => {
  it('splits the Watchlist from a separately-labeled Searched tickers group', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    const watchlist = await screen.findByRole('group', { name: 'Watchlist' })
    const searched = await screen.findByRole('group', { name: 'Searched tickers' })
    expect(within(watchlist).getByRole('button', { name: /^TCB/ })).toBeInTheDocument()
    expect(within(searched).getByRole('button', { name: /^FPT/ })).toBeInTheDocument()
    expect(within(watchlist).queryByRole('button', { name: /^FPT/ })).not.toBeInTheDocument()
  })

  it('does not render a Searched tickers group when nothing has been searched in yet', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    expect(screen.queryByRole('group', { name: 'Searched tickers' })).not.toBeInTheDocument()
  })

  it('filtering the search input narrows both the Searched tickers group and the Watchlist', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockImplementation((ticker) =>
      Promise.resolve({ ticker, status: 'ok', rows_loaded: 300 }),
    )

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    const input = screen.getByLabelText(/search ticker/i)
    const loadButton = screen.getByRole('button', { name: /^load$/i })

    await userEvent.type(input, 'FPT')
    await userEvent.click(loadButton)
    await waitFor(() => expect(screen.getByRole('button', { name: /^FPT/ })).toBeInTheDocument())

    await userEvent.type(input, 'ABC')
    await userEvent.click(loadButton)
    await waitFor(() => expect(screen.getByRole('button', { name: /^ABC/ })).toBeInTheDocument())

    // Filter without submitting — narrows both groups.
    await userEvent.clear(input)
    await userEvent.type(input, 'FP')

    const searched = screen.getByRole('group', { name: 'Searched tickers' })
    expect(within(searched).getByRole('button', { name: /^FPT/ })).toBeInTheDocument()
    expect(within(searched).queryByRole('button', { name: /^ABC/ })).not.toBeInTheDocument()
    // "TCB" doesn't contain the typed substring, so the Watchlist drops it.
    const watchlist = screen.getByRole('group', { name: 'Watchlist' })
    expect(within(watchlist).queryByRole('button', { name: /^TCB/ })).not.toBeInTheDocument()

    // Clearing the filter brings the Watchlist back.
    await userEvent.clear(input)
    expect(within(watchlist).getByRole('button', { name: /^TCB/ })).toBeInTheDocument()
  })

  it('filtering keeps only the Watchlist chips whose symbol contains the typed text', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'HPG', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
      ],
    })
    mockFreshData()

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    await userEvent.type(screen.getByLabelText(/search ticker/i), 'ib')

    const watchlist = screen.getByRole('group', { name: 'Watchlist' })
    expect(within(watchlist).getByRole('button', { name: /^VIB/ })).toBeInTheDocument()
    expect(within(watchlist).queryByRole('button', { name: /^TCB/ })).not.toBeInTheDocument()
    expect(within(watchlist).queryByRole('button', { name: /^HPG/ })).not.toBeInTheDocument()
  })

  it('explains an empty result and points at Load when the filter matches no loaded ticker', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    await userEvent.type(screen.getByLabelText(/search ticker/i), 'ZZZ')

    expect(screen.getByText(/no loaded tickers match "ZZZ"/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^TCB/ })).not.toBeInTheDocument()
  })

  it('announces the combined filtered count across the Watchlist even with nothing searched in', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'HPG', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
      ],
    })
    mockFreshData()

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })

    await userEvent.type(screen.getByLabelText(/search ticker/i), 'T')

    expect(await screen.findByText('1 of 3 tickers')).toBeInTheDocument()
  })

  it('does not say "no loaded tickers match" when only the Searched group has a match', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))
    await screen.findByRole('group', { name: 'Searched tickers' })

    // "FP" matches the searched-in FPT but nothing in the Watchlist (TCB).
    await userEvent.type(input, 'FP')

    const searched = screen.getByRole('group', { name: 'Searched tickers' })
    expect(within(searched).getByRole('button', { name: /^FPT/ })).toBeInTheDocument()
    expect(screen.queryByText(/no loaded tickers match/i)).not.toBeInTheDocument()
  })

  it('counts a ticker shown in both groups once in the announced total', async () => {
    // Once /tickers refetches a searched-in ticker as loaded it appears in
    // the Watchlist AND the Searched list; without dedupe this would read
    // "2 of 3 tickers".
    vi.spyOn(tickersApi, 'fetchTickers')
      .mockResolvedValueOnce({
        tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
      })
      .mockResolvedValue({
        tickers: [
          { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
          { ticker: 'FPT', in_training_set: false, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        ],
      })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })

    renderPanel()
    await screen.findByRole('button', { name: /^TCB/ })
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))
    const watchlist = await screen.findByRole('group', { name: 'Watchlist' })
    await waitFor(() => expect(within(watchlist).getByRole('button', { name: /^FPT/ })).toBeInTheDocument())

    await userEvent.type(input, 'FP')

    expect(await screen.findByText('1 of 2 tickers')).toBeInTheDocument()
  })

  it('announces the filtered count for screen readers as the user types', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [] })
    vi.spyOn(tickersApi, 'loadTicker').mockImplementation((ticker) =>
      Promise.resolve({ ticker, status: 'ok', rows_loaded: 300 }),
    )

    renderPanel()
    const input = screen.getByLabelText(/search ticker/i)
    const loadButton = screen.getByRole('button', { name: /^load$/i })

    await userEvent.type(input, 'FPT')
    await userEvent.click(loadButton)
    await waitFor(() => expect(screen.getByRole('button', { name: /^FPT/ })).toBeInTheDocument())

    await userEvent.type(input, 'ABC')
    await userEvent.click(loadButton)
    await waitFor(() => expect(screen.getByRole('button', { name: /^ABC/ })).toBeInTheDocument())

    await userEvent.clear(input)
    await userEvent.type(input, 'FP')

    expect(await screen.findByText('1 of 2 tickers')).toBeInTheDocument()
  })
})

// Adjacent fix (found live, not caused by redesign-dashboard-visual-look):
// AIInsightPanel's first fetch for any given ticker was always cold —
// unlike Prediction/Chart, nothing warmed `useTickerInsight`'s cache ahead
// of selection — forcing a visible loading-placeholder flash on that
// ticker's first selection. TickerChip now prefetches insight the same
// way it already prefetches prediction/history for freshness.
describe('TickerPanel insight prefetch', () => {
  it('prefetches AI insight for every Watchlist ticker on render, not just the selected one', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
      ],
    })
    mockFreshData()
    const insightSpy = tickersApi.fetchTickerInsight

    renderPanel({ selectedTicker: null })

    await waitFor(() => {
      expect(insightSpy).toHaveBeenCalledWith('TCB')
      expect(insightSpy).toHaveBeenCalledWith('VIB')
    })
  })

  it('does not prefetch insight for a ticker that is not loaded', async () => {
    // An unloaded ticker does not appear as a chip, so it is never selected
    // and no prefetch is triggered. Verify by rendering with only an unloaded
    // entry and asserting the insight API is not called.
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', in_training_set: true, loaded: false, features_computed: null, last_loaded_at: null }],
    })
    const insightSpy = vi.spyOn(tickersApi, 'fetchTickerInsight')

    renderPanel()
    // Allow any async work to settle
    await new Promise((r) => setTimeout(r, 50))

    expect(insightSpy).not.toHaveBeenCalled()
  })
})

// ticker-manual-refresh: a "Refresh" action on an already-loaded ticker
// that re-runs the existing /load flow (tasks.md sections 2/3/5).
describe('TickerPanel refresh action', () => {
  it('shows a Refresh action only for a loaded ticker, not an unloaded one', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', in_training_set: true, loaded: false, features_computed: null, last_loaded_at: null },
      ],
    })
    mockFreshData()

    renderPanel()

    expect(await screen.findByRole('button', { name: 'Refresh TCB' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Refresh VIB' })).not.toBeInTheDocument()
  })

  it('clicking Refresh calls POST /tickers/{ticker}/load without changing the selection', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    const loadSpy = vi
      .spyOn(tickersApi, 'loadTicker')
      .mockResolvedValue({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })

    const { onSelectTicker } = renderPanel()
    const refreshButton = await screen.findByRole('button', { name: 'Refresh TCB' })
    await userEvent.click(refreshButton)

    await waitFor(() => expect(loadSpy).toHaveBeenCalledWith('TCB'))
    expect(onSelectTicker).not.toHaveBeenCalled()
  })

  it('disables Refresh while its own request is in flight', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    let resolveLoad
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(
      new Promise((resolve) => {
        resolveLoad = resolve
      }),
    )

    renderPanel()
    const refreshButton = await screen.findByRole('button', { name: 'Refresh TCB' })
    await userEvent.click(refreshButton)

    await waitFor(() => expect(refreshButton).toBeDisabled())

    resolveLoad({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })
    await waitFor(() => expect(refreshButton).not.toBeDisabled())
  })

  it('reuses the existing rate-limited message when Refresh does not complete with status ok', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'rate_limited' })

    renderPanel()
    const refreshButton = await screen.findByRole('button', { name: 'Refresh TCB' })
    await userEvent.click(refreshButton)

    expect(await screen.findByText(/try again in a moment/i)).toBeInTheDocument()
  })

  it('does not invalidate history/prediction/insight when Refresh completes with a non-ok status', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'rate_limited' })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    render(
      <QueryClientProvider client={queryClient}>
        <TickerPanel selectedTicker="TCB" onSelectTicker={vi.fn()} />
      </QueryClientProvider>,
    )

    const refreshButton = await screen.findByRole('button', { name: 'Refresh TCB' })
    invalidateSpy.mockClear() // ignore invalidations from the initial catalog/freshness fetch
    await userEvent.click(refreshButton)

    await screen.findByText(/try again in a moment/i)
    expect(invalidateSpy).not.toHaveBeenCalled()
  })

  it('invalidates history/prediction/insight identically to a first-time load when Refresh succeeds', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'TCB', status: 'ok', rows_loaded: 300 })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    render(
      <QueryClientProvider client={queryClient}>
        <TickerPanel selectedTicker="TCB" onSelectTicker={vi.fn()} />
      </QueryClientProvider>,
    )

    const refreshButton = await screen.findByRole('button', { name: 'Refresh TCB' })
    await userEvent.click(refreshButton)

    await waitFor(() => {
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
  })

  it('shows a relative last-loaded time for a loaded ticker', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', in_training_set: true, loaded: true, features_computed: true, last_loaded_at: new Date().toISOString() },
      ],
    })
    mockFreshData()

    renderPanel()

    expect(await screen.findByText(/^Loaded /)).toBeInTheDocument()
  })
})
