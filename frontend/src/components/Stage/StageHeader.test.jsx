import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { StageHeader } from './StageHeader'
import { FAVORITES_STORAGE_KEY, resetFavoritesCache } from '../../hooks/useFavorites'
import * as tickersApi from '../../api/tickers'
import { catalogEntry, ineligible, renderWithQuery } from '../../test/railFixtures'

const history = (ticker = 'TCB') => ({
  ticker,
  rows: [{ date: '2026-10-06', open: 42, high: 43, low: 41, close: 42.55, volume: 120 }],
})
const range = (overrides = {}) => ({
  ticker: 'TCB', as_of: '2026-10-06', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
  range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 }, ...overrides,
})

function renderHeader(ticker, { catalog = [], rangeResult = range() } = {}) {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: catalog })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue(history(ticker ?? 'TCB'))
  vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeResult)
  const debate = vi.spyOn(tickersApi, 'runDebateAnalysis')
  return { debate, ...renderWithQuery(<StageHeader ticker={ticker} />) }
}

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  resetFavoritesCache()
})

describe('StageHeader', () => {
  it('is the one h1: the ticker, with the last close beside it', async () => {
    renderHeader('TCB', { catalog: [catalogEntry('TCB')] })

    expect(await screen.findByRole('heading', { level: 1, name: 'TCB' })).toBeInTheDocument()
    expect(await screen.findByText('42.55')).toBeInTheDocument()
  })

  it('reads "As of 2026-10-06 · current" at age 0', async () => {
    renderHeader('TCB', { catalog: [catalogEntry('TCB')] })

    expect(await screen.findByText('As of 2026-10-06 · current')).toBeInTheDocument()
    expect(screen.queryByText('Stale')).not.toBeInTheDocument()
  })

  it('reads "As of 2026-09-07 · 21 sessions old" with the text Stale beside it, and still shows the chart data', async () => {
    renderHeader('TCB', {
      catalog: [catalogEntry('TCB', { eligibility: ineligible(['stale'], 21) })],
      rangeResult: range({ as_of: '2026-09-07', status: 'ineligible', range_5s_pct: null, reasons: ['stale'] }),
    })

    expect(await screen.findByText('As of 2026-09-07 · 21 sessions old')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('42.55')).toBeInTheDocument()
  })

  it('says "1 session old" at age 1', async () => {
    renderHeader('TCB', {
      catalog: [catalogEntry('TCB', { eligibility: { eligible: true, reasons: [], as_of: '2026-10-05', age_sessions: 1 } })],
    })

    expect(await screen.findByText('As of 2026-10-06 · 1 session old')).toBeInTheDocument()
  })

  it('shows the date alone, with no age and no invented number, for a ticker with no catalog entry', async () => {
    renderHeader('TCB', { catalog: [] })

    expect(await screen.findByText('As of 2026-10-06')).toBeInTheDocument()
    expect(screen.queryByText(/session/)).not.toBeInTheDocument()
    expect(screen.queryByText(/current/)).not.toBeInTheDocument()
  })

  it('takes Stale from /range for a ticker with no catalog entry', async () => {
    renderHeader('TCB', {
      catalog: [],
      rangeResult: range({ as_of: '2026-09-07', status: 'ineligible', range_5s_pct: null, reasons: ['stale'] }),
    })

    expect(await screen.findByText('As of 2026-09-07')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
  })

  it('is available before any debate has run, and issues no debate request', async () => {
    const { debate } = renderHeader('TCB', { catalog: [catalogEntry('TCB')] })

    await screen.findByText('As of 2026-10-06 · current')

    expect(debate).not.toHaveBeenCalled()
  })

  it('keeps its shape with placeholders when no ticker is selected', async () => {
    renderHeader(null)

    expect(screen.getByRole('heading', { level: 1, name: 'No ticker selected' })).toBeInTheDocument()
    expect(screen.getByText('As of —')).toBeInTheDocument()
    expect(screen.getByText('—', { selector: '.stage-header__close' })).toBeInTheDocument()
  })

  it('shows no status dot, direction mark or percentage', async () => {
    const { container } = renderHeader('TCB', { catalog: [catalogEntry('TCB', { eligibility: ineligible(['stale'], 21) })] })
    await screen.findByText('Stale')

    expect(container).not.toHaveTextContent(/[↑↓▲▼→%]/)
    expect(container.querySelector('[class*="dot"], [data-status], [data-freshness], [data-direction]')).toBeNull()
  })
})

describe('StageHeader favorite star', () => {
  const star = () => screen.getByRole('button', { name: 'Favorite TCB' })

  it('sits after the ticker, the close and the data date, and is not pressed for a ticker that is not a favorite', async () => {
    renderHeader('TCB', { catalog: [catalogEntry('TCB')] })
    const date = await screen.findByText('As of 2026-10-06 · current')

    expect(star()).toHaveAttribute('aria-pressed', 'false')
    expect(date.compareDocumentPosition(star()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('is pressed for a favorite', async () => {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(['TCB']))
    renderHeader('TCB', { catalog: [catalogEntry('TCB')] })
    await screen.findByText('As of 2026-10-06 · current')

    expect(star()).toHaveAttribute('aria-pressed', 'true')
  })

  it('toggles on and off, stores the list, and makes no request and no debate', async () => {
    const { debate } = renderHeader('TCB', { catalog: [catalogEntry('TCB')] })
    await screen.findByText('As of 2026-10-06 · current')
    const requests = tickersApi.fetchTickerHistory.mock.calls.length

    await userEvent.click(star())
    expect(star()).toHaveAttribute('aria-pressed', 'true')
    expect(JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY))).toEqual(['TCB'])

    await userEvent.click(star())
    expect(star()).toHaveAttribute('aria-pressed', 'false')
    expect(JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY))).toEqual([])
    expect(tickersApi.fetchTickerHistory.mock.calls.length).toBe(requests)
    expect(debate).not.toHaveBeenCalled()
  })

  it('is in the heading row but not inside the h1, so the page title stays just the ticker', async () => {
    renderHeader('TCB', { catalog: [catalogEntry('TCB')] })
    await screen.findByText('As of 2026-10-06 · current')

    expect(screen.getByRole('heading', { level: 1 })).toHaveAccessibleName('TCB')
    expect(screen.getByRole('heading', { level: 1 })).not.toContainElement(star())
  })

  it('is absent when no ticker is selected', () => {
    renderHeader(null)

    expect(screen.queryByRole('button', { name: /favorite/i })).not.toBeInTheDocument()
  })
})
