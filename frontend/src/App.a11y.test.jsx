import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { computeAccessibleName } from 'dom-accessibility-api'
import App from './App'
import * as tickersApi from './api/tickers'
import { catalogEntry } from './test/railFixtures'
import { populated } from './test/debateFixtures'
import { resetViewport, setViewport } from './test/viewport'

const TICKERS = [catalogEntry('TCB'), catalogEntry('VIB')]

function arrangeApi() {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: TICKERS })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockImplementation(async (ticker) => ({
    ticker,
    rows: [{ date: '2026-08-10', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
  }))
  vi.spyOn(tickersApi, 'fetchTickerRange').mockImplementation(async (ticker) => ({
    ticker, as_of: '2026-08-10', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
    range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 },
  }))
  vi.spyOn(tickersApi, 'runDebateAnalysis').mockResolvedValue(populated({ ticker: 'TCB', data_as_of: '2026-08-10', data_age_sessions: 0 }))
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

const nameOf = (element) => computeAccessibleName(element)

// Presses Tab until `matches` accepts the focused element; fails with the names seen so far.
async function tabTo(matches, { limit = 80 } = {}) {
  const seen = []
  for (let i = 0; i < limit; i += 1) {
    await userEvent.tab()
    const focused = document.activeElement
    seen.push(nameOf(focused) || focused.tagName)
    if (matches(focused)) return focused
  }
  throw new Error(`Never reached the target by Tab. Focus visited: ${seen.join(' | ')}`)
}
const named = (name) => (element) => nameOf(element) === name

beforeEach(() => {
  vi.restoreAllMocks()
  arrangeApi()
  setViewport(1440)
})

afterEach(() => {
  resetViewport()
  document.documentElement.removeAttribute('data-theme')
  localStorage.clear()
  delete HTMLElement.prototype.scrollHeight
  delete HTMLElement.prototype.clientHeight
})

describe('landmarks and names', () => {
  it('exposes header, nav, main and aside landmarks and exactly one h1', async () => {
    const { queryClient } = renderApp()
    await vi.waitFor(() => expect(queryClient.getQueryData(['tickers'])).toBeDefined())
    await userEvent.type(screen.getByLabelText(/search ticker/i), 'tcb{Enter}')
    await screen.findByRole('heading', { level: 1, name: 'TCB' })

    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Tickers' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Verdict' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('search')).toBeInTheDocument()
  })

  it('names the brand as text, not as a heading', () => {
    renderApp()

    expect(screen.getByText('Stock Foresight')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Stock Foresight' })).not.toBeInTheDocument()
  })

  it('gives every control an accessible name', async () => {
    const { queryClient } = renderApp()
    await vi.waitFor(() => expect(queryClient.getQueryData(['tickers'])).toBeDefined())
    await userEvent.type(screen.getByLabelText(/search ticker/i), 'tcb{Enter}')
    await screen.findByRole('button', { name: 'Analyse TCB' })

    const controls = [
      ...screen.getAllByRole('button'),
      ...screen.getAllByRole('combobox'),
      ...screen.getAllByRole('textbox'),
    ]
    expect(controls.length).toBeGreaterThan(8)
    for (const control of controls) expect(nameOf(control), control.outerHTML.slice(0, 80)).not.toBe('')
  })

  it('names the sort control, the chart history group and the theme toggle', async () => {
    renderApp()

    expect(screen.getByRole('combobox', { name: 'Sort tickers' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Chart history' })).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: 'Dark theme' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
  })

  it('the theme toggle is pressed after it is used, and the page follows', async () => {
    renderApp()

    await userEvent.click(screen.getByRole('button', { name: 'Dark theme' }))

    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })

  it('offers the full disclaimer through a native disclosure whose summary comes first', async () => {
    renderApp()

    const details = screen.getByText('About this analysis').closest('details')

    expect(details.firstElementChild.tagName).toBe('SUMMARY')
  })
})

describe('keyboard-only walkthrough', () => {
  it('selects a ticker, analyses, expands a card and toggles the theme with Tab, Shift+Tab, Enter and Space', async () => {
    // Long text in every card, so each has a "Show more".
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => 200 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 100 })
    const { queryClient } = renderApp()
    await vi.waitFor(() => expect(queryClient.getQueryData(['tickers'])).toBeDefined())

    // The first focusable control is the search; Enter on a symbol in the Rail selects it.
    const search = await tabTo(named('Search ticker'))
    await userEvent.keyboard('tcb{Enter}')
    expect(await screen.findByRole('heading', { level: 1, name: 'TCB' })).toBeInTheDocument()
    expect(search).toHaveValue('')

    // The theme toggle comes next, in the topbar, before the Rail.
    const toggle = await tabTo(named('Dark theme'))
    await userEvent.keyboard(' ')
    expect(toggle).toHaveAttribute('aria-pressed', 'true')

    // Then the Rail, the Stage and the Verdict panel, in reading order, down to Analyse.
    const order = []
    await tabTo((element) => {
      order.push(nameOf(element))
      return nameOf(element) === 'Analyse TCB'
    })
    expect(order.indexOf('Sort tickers')).toBeGreaterThanOrEqual(0)
    expect(order.indexOf('Sort tickers')).toBeLessThan(order.indexOf('Reset zoom'))
    expect(order.indexOf('Reset zoom')).toBeLessThan(order.indexOf('Analyse TCB'))
    await userEvent.keyboard('{Enter}')
    await screen.findByText('Bullish lean')

    // Expand an agent card, then close it again.
    const more = await tabTo(named('Show more'))
    await userEvent.keyboard('{Enter}')
    expect(more).toHaveAttribute('aria-expanded', 'true')
    await userEvent.keyboard(' ')
    expect(more).toHaveAttribute('aria-expanded', 'false')

    // Shift+Tab walks back the way it came.
    await userEvent.tab({ shift: true })
    expect(document.activeElement).not.toBe(more)
  })

  it('on a phone, picks a ticker from the combobox and moves between the agent tabs with the arrow keys', async () => {
    setViewport(390)
    const { queryClient } = renderApp()
    await vi.waitFor(() => expect(queryClient.getQueryData(['tickers'])).toBeDefined())

    const search = await tabTo(named('Search ticker'))
    await userEvent.keyboard('tc')
    expect(search).toHaveAttribute('aria-expanded', 'true')
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(await screen.findByRole('heading', { level: 1, name: 'TCB' })).toBeInTheDocument()

    await tabTo(named('Analyse TCB'))
    await userEvent.keyboard('{Enter}')
    await screen.findByText('Bullish lean')

    const firstTab = await tabTo((element) => element.getAttribute('role') === 'tab')
    expect(firstTab).toHaveAccessibleName('Technical Signal')
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'News Context' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'News Context' })).toHaveFocus()
  })

  it('at 900px the drawer is reachable from the keyboard alone, and closes on Escape with focus back on its button', async () => {
    setViewport(900)
    const { queryClient } = renderApp()
    await vi.waitFor(() => expect(queryClient.getQueryData(['tickers'])).toBeDefined())

    const button = await tabTo(named('Tickers'))
    await userEvent.keyboard('{Enter}')
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const row = await tabTo((element) => nameOf(element).startsWith('TCB'))
    expect(row).toBeVisible()

    await userEvent.keyboard('{Escape}')

    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(button).toHaveFocus()
  })
})
