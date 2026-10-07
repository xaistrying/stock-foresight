import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import * as tickersApi from './api/tickers'
import { INLINE_DISCLAIMER } from './lib/disclaimer'
import { catalogEntry } from './test/railFixtures'
import { MOCK_RESULT, populated } from './test/debateFixtures'
import { resetViewport, setViewport } from './test/viewport'

// The four layout modes against the composed app: each single-place element renders once whatever the
// mode, and DOM order is the reading order in every mode (so tab order and visual order agree).
const MODES = [
  [1440, 'wide'],
  [1300, 'collapsed'],
  [900, 'drawer'],
  [390, 'phone'],
]

function arrangeApi() {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: [catalogEntry('TCB')] })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
    ticker: 'TCB',
    rows: [{ date: '2026-08-10', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
  })
  vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({
    ticker: 'TCB', as_of: '2026-08-10', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
    range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 },
  })
  vi.spyOn(tickersApi, 'runDebateAnalysis').mockResolvedValue(
    populated({ ticker: 'TCB', data_as_of: '2026-08-10', data_age_sessions: 0 }),
  )
  vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue({ ticker: 'TCB', running: true, stage: 'round1', elapsed_ms: 100 })
}

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
  return { ...view, queryClient }
}

// Selecting through the search works at every width (Enter on a symbol in the list), so one flow
// serves all modes. The catalog is awaited first: Enter on a symbol not yet listed would load it.
async function openWithResult(queryClient) {
  await vi.waitFor(() => expect(queryClient.getQueryData(['tickers'])).toBeDefined())
  await userEvent.type(await screen.findByLabelText(/search ticker/i), 'tcb{Enter}')
  await userEvent.click(await screen.findByRole('button', { name: 'Analyse TCB' }))
  await screen.findByText('Bullish lean')
}

const verdictPanel = () => screen.getByRole('complementary', { name: 'Verdict' })

beforeEach(() => {
  vi.restoreAllMocks()
  arrangeApi()
})

afterEach(() => {
  resetViewport()
})

describe.each(MODES)('at %ipx (%s mode) with a result present', (width) => {
  beforeEach(() => setViewport(width))

  it('shows the range check once, Key tension once and the Verdict panel\'s inline disclaimer once', async () => {
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    expect(screen.getAllByText(/34 of the last 50 five-session moves stayed inside it/)).toHaveLength(1)
    expect(screen.getAllByText(MOCK_RESULT.synthesis.key_tension)).toHaveLength(1)
    expect(within(verdictPanel()).getAllByText(INLINE_DISCLAIMER)).toHaveLength(1)
    expect(screen.getAllByRole('heading', { name: 'Key tension' })).toHaveLength(1)
  })

  it('shows the Debate matrix once, and tells the same story as the panel from the same run', async () => {
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    expect(screen.getAllByRole('region', { name: 'Debate' })).toHaveLength(1)
    expect(tickersApi.runDebateAnalysis).toHaveBeenCalledTimes(1)
  })
})

describe('layout-mode specific structure', () => {
  it('on a phone shows the Debate matrix as a tablist of three agents, and nowhere else', async () => {
    setViewport(390)
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    expect(screen.getByRole('tablist', { name: 'Agents' })).toBeInTheDocument()
    expect(screen.getAllByRole('tab')).toHaveLength(3)
  })

  it.each([[1440], [1300], [900]])('at %ipx shows three agent columns of cards, not tabs', async (width) => {
    setViewport(width)
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(6)
  })

  it('renders the Rail as a column at 1440px, collapsed at 1300px, a drawer at 900px and not at all on a phone', async () => {
    const modes = {}
    for (const [width] of MODES) {
      setViewport(width)
      const { unmount } = renderApp()
      await screen.findByLabelText(/search ticker/i)
      const rail = document.querySelector('.rail')
      modes[width] = rail ? rail.getAttribute('data-mode') : null
      unmount()
      vi.restoreAllMocks()
      arrangeApi()
    }

    expect(modes).toEqual({ 1440: 'wide', 1300: 'collapsed', 900: 'drawer', 390: null })
  })
})

describe('reading order equals visual order in every mode', () => {
  const follows = (earlier, later) =>
    expect(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

  it.each([[1440], [1300], [900]])('at %ipx: topbar, Rail, Stage header, chart, Verdict panel, matrix', async (width) => {
    setViewport(width)
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    const order = [
      screen.getByRole('banner'),
      // A closed drawer is hidden, and a hidden element has no accessible name, so no name here.
      screen.getByRole('navigation', { hidden: true }),
      screen.getByRole('heading', { level: 1, name: 'TCB' }),
      screen.getByRole('region', { name: /price chart/i }),
      verdictPanel(),
      screen.getByRole('region', { name: 'Debate' }),
    ]
    for (let i = 1; i < order.length; i += 1) follows(order[i - 1], order[i])
  })

  it('on a phone: topbar, Stage header, range block, chart, Verdict panel, matrix', async () => {
    setViewport(390)
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    const order = [
      screen.getByRole('banner'),
      screen.getByRole('heading', { level: 1, name: 'TCB' }),
      screen.getByRole('region', { name: 'Range for TCB' }),
      screen.getByRole('region', { name: /price chart/i }),
      verdictPanel(),
      screen.getByRole('region', { name: 'Debate' }),
    ]
    for (let i = 1; i < order.length; i += 1) follows(order[i - 1], order[i])
  })

  it('on a phone the range block stands outside the panel, so it carries the disclaimer itself', async () => {
    setViewport(390)
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    const block = screen.getByRole('region', { name: 'Range for TCB' })
    expect(within(block).getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
    expect(within(verdictPanel()).queryByText(/Range hit-rate/)).not.toBeInTheDocument()
  })

  it('at wider widths the range block is inside the Verdict panel', async () => {
    setViewport(1440)
    const { queryClient } = renderApp()
    await openWithResult(queryClient)

    expect(within(verdictPanel()).getByRole('region', { name: 'Range for TCB' })).toBeInTheDocument()
  })
})
