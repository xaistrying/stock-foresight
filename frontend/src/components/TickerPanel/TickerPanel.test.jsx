import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TickerPanel } from './TickerPanel'
import * as tickersApi from '../../api/tickers'

// Mirrors GET /tickers/{ticker}/prediction and /history enough for the
// freshness computation (useTickerFreshness) to resolve deterministically
// in tests, without a real backend.
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
  it('renders one chip per ticker from GET /tickers, always visible', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', loaded: false, features_computed: null, last_loaded_at: null },
      ],
    })
    mockFreshData()

    renderPanel()

    expect(await screen.findByRole('button', { name: /TCB/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /VIB/ })).toBeInTheDocument()
  })

  it('shows "Not loaded" for a never-loaded catalog ticker', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', loaded: false, features_computed: null, last_loaded_at: null }],
    })

    renderPanel()

    expect(await screen.findByText('Not loaded')).toBeInTheDocument()
  })

  it('clicking an already-loaded chip selects it directly, without a /load call', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    const loadSpy = vi.spyOn(tickersApi, 'loadTicker')

    const { onSelectTicker } = renderPanel()
    const chip = await screen.findByRole('button', { name: /TCB/ })
    await userEvent.click(chip)

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
    expect(loadSpy).not.toHaveBeenCalled()
  })

  it('clicking an unloaded chip triggers /load and selects on success', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', loaded: false, features_computed: null, last_loaded_at: null }],
    })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'ok', rows_loaded: 300 })

    const { onSelectTicker } = renderPanel()
    const chip = await screen.findByRole('button', { name: /VIB/ })
    await userEvent.click(chip)

    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('VIB'))
  })

  it('shows a distinct message per load-failure status, not a generic one', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'VIB', loaded: false, features_computed: null, last_loaded_at: null }],
    })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VIB', status: 'rate_limited' })

    const { onSelectTicker } = renderPanel()
    const chip = await screen.findByRole('button', { name: /VIB/ })
    await userEvent.click(chip)

    expect(await screen.findByText(/try again in a moment/i)).toBeInTheDocument()
    expect(onSelectTicker).not.toHaveBeenCalled()
  })

  it('search resolves an already-known ticker directly, without a new /load call', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [{ ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()
    const loadSpy = vi.spyOn(tickersApi, 'loadTicker')

    const { onSelectTicker } = renderPanel()
    await screen.findByRole('button', { name: /TCB/ })

    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'TCB')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    expect(onSelectTicker).toHaveBeenCalledWith('TCB')
    expect(loadSpy).not.toHaveBeenCalled()
  })

  it('searching a new ticker triggers /load and adds it to the selectable list on success', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [] })
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'FPT', status: 'ok', rows_loaded: 300 })

    const { onSelectTicker } = renderPanel()
    const input = screen.getByLabelText(/search ticker/i)
    await userEvent.type(input, 'FPT')
    await userEvent.click(screen.getByRole('button', { name: /^load$/i }))

    await waitFor(() => expect(onSelectTicker).toHaveBeenCalledWith('FPT'))
    expect(await screen.findByRole('button', { name: /FPT/ })).toBeInTheDocument()
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
      tickers: [{ ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()

    renderPanel()

    const chip = await screen.findByRole('button', { name: /TCB/ })
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
      tickers: [{ ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' }],
    })
    mockFreshData()

    renderPanel()
    await screen.findByRole('button', { name: /TCB/ })

    expect(screen.getByText('Fresh')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('Loading')).toBeInTheDocument()
  })

  it('marks the selected ticker distinctly from unselected ones', async () => {
    vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({
      tickers: [
        { ticker: 'TCB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
        { ticker: 'VIB', loaded: true, features_computed: true, last_loaded_at: '2026-08-10' },
      ],
    })
    mockFreshData()

    renderPanel({ selectedTicker: 'TCB' })

    const tcbChip = await screen.findByRole('button', { name: /TCB/ })
    const vibChip = screen.getByRole('button', { name: /VIB/ })
    expect(tcbChip).toHaveAttribute('aria-pressed', 'true')
    expect(vibChip).toHaveAttribute('aria-pressed', 'false')
  })
})
