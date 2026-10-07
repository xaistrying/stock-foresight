import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import * as tickersApi from './api/tickers'
import { ApiError } from './api/client'
import { FULL_DISCLAIMER, INLINE_DISCLAIMER } from './lib/disclaimer'
import { catalogEntry, ineligible } from './test/railFixtures'
import { LABELS, insufficient, oneDegraded, populated, withVerdict } from './test/debateFixtures'
import { resetViewport, setViewport } from './test/viewport'

// The whole page, in every Verdict state and with a populated Rail: nothing outside a stance chip, a
// verdict badge or an agent card may imply direction, and nothing may read as investment advice, a
// forecast or a Confidence figure (design Decision 11, Rules 2, 4 and 6).
const CATALOG = [
  catalogEntry('TCB', { in_training_set: true }),
  catalogEntry('VIB', { eligibility: ineligible(['stale'], 21) }),
  catalogEntry('HPG', { eligibility: ineligible(['delisted', 'stale'], 24) }),
  catalogEntry('VCB'),
]

function arrangeApi(run) {
  vi.spyOn(tickersApi, 'fetchTickers').mockResolvedValue({ tickers: CATALOG })
  vi.spyOn(tickersApi, 'fetchTickerHistory').mockImplementation(async (ticker) => ({
    ticker,
    rows: [{ date: '2026-08-10', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }],
  }))
  vi.spyOn(tickersApi, 'fetchTickerRange').mockImplementation(async (ticker) => ({
    ticker, as_of: '2026-08-10', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
    range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 },
  }))
  vi.spyOn(tickersApi, 'runDebateAnalysis').mockImplementation(run)
  vi.spyOn(tickersApi, 'getDebateProgress').mockResolvedValue({ ticker: 'TCB', running: true, stage: 'round2', elapsed_ms: 100 })
}

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

const selectRow = async (name) => userEvent.click(await screen.findByRole('button', { name }))
const analyse = async () => userEvent.click(await screen.findByRole('button', { name: 'Analyse TCB' }))

// Every state, as a way to reach it from a fresh page.
const STATES = {
  none: { run: () => Promise.reject(new Error('unused')), reach: async () => screen.findByRole('button', { name: /^TCB/ }) },
  ready: {
    run: () => Promise.reject(new Error('unused')),
    reach: async () => {
      await selectRow(/^TCB/)
      await screen.findByRole('button', { name: 'Analyse TCB' })
    },
  },
  running: {
    run: () => new Promise(() => {}),
    reach: async () => {
      await selectRow(/^TCB/)
      await analyse()
      await screen.findByText('Comparing positions…', {}, { timeout: 3000 }).catch(() => screen.findByText('Running agents…'))
    },
  },
  result: {
    run: async () => populated({ data_as_of: '2026-08-10', data_age_sessions: 0 }),
    reach: async () => {
      await selectRow(/^TCB/)
      await analyse()
      await screen.findByText('Bullish lean')
    },
  },
  partial: {
    run: async () => oneDegraded({ data_as_of: '2026-08-10', data_age_sessions: 0 }),
    reach: async () => {
      await selectRow(/^TCB/)
      await analyse()
      await screen.findByText('News Context unavailable')
    },
  },
  insufficient: {
    run: () => Promise.reject(new Error('unused')),
    reach: async () => {
      await selectRow(/^VIB/)
      await screen.findByText('Insufficient data')
    },
  },
  failed: {
    run: async () => {
      throw new ApiError('busy', { status: 429, body: { code: 'debate_busy' } })
    },
    reach: async () => {
      await selectRow(/^TCB/)
      await analyse()
      await screen.findByText('Could not run the analysis:')
    },
  },
}

const withoutDisclaimers = (text) => text.replace(INLINE_DISCLAIMER, '').replaceAll(INLINE_DISCLAIMER, '').replace(FULL_DISCLAIMER, '')

// Arrows belong to stance chips, the verdict badge's glyph and an agent card's head, and nowhere else.
function arrowsOutsideMarks(container) {
  const found = []
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (/[↑↓→]/.test(node.textContent) && !node.parentElement.closest('.stance-chip, .verdict-badge, .agent-card__head')) {
      found.push(node.textContent.trim())
    }
  }
  return found
}

beforeEach(() => {
  vi.restoreAllMocks()
  setViewport(1440)
})

afterEach(resetViewport)

describe('no Rail, Stage or Verdict element implies direction except stance and verdict marks', () => {
  it.each(Object.keys(STATES))('%s state', async (name) => {
    arrangeApi(STATES[name].run)
    const { container } = renderApp()
    await STATES[name].reach()
    const text = withoutDisclaimers(container.textContent)

    expect(text).not.toMatch(/[+\-−]\d+(\.\d+)?%/) // a signed percentage
    expect(text).not.toMatch(/[▲▼]/)
    expect(text).not.toMatch(/confiden(ce|t)/i)
    expect(text).not.toMatch(/predict|forecast|expected/i)
    expect(text).not.toMatch(/market sentiment/i)
    expect(container.querySelector('[data-direction]')).toBeNull()
    expect(container.querySelector('[class*="dot"], [role="img"][aria-label*="status" i]')).toBeNull()
    expect(arrowsOutsideMarks(container)).toEqual([])
  })

  it('the Rail rows carry no arrow, percentage, dot or direction colour class', async () => {
    arrangeApi(STATES.none.run)
    renderApp()
    await screen.findByRole('button', { name: /^TCB/ })

    const rail = screen.getByRole('navigation', { name: 'Tickers' })

    expect(rail).not.toHaveTextContent(/[↑↓→▲▼%]/)
    expect(rail.querySelector('[class*="bull"], [class*="bear"], [class*="dot"], [data-status]')).toBeNull()
  })

  it('a failure is named in words and its classes carry no up or down tone', async () => {
    arrangeApi(STATES.failed.run)
    renderApp()
    await STATES.failed.reach()

    const alert = screen.getAllByRole('alert').find((el) => /Could not run the analysis/.test(el.textContent))

    expect(alert.textContent).toMatch(/already running/)
    expect(alert.outerHTML).not.toMatch(/bull|bear|--up|--down|candle/)
  })
})

describe('fixed dashboard text has no transaction verbs, enum text or Confidence (Rule 6)', () => {
  const GUARDS = [/\b(buy|sell|hold)\b/i, /[A-Z]+_SIGNAL/, /\bconfiden(ce|t)\b/i]

  it.each(Object.keys(LABELS))('for %s, across the topbar, Rail, Stage, Verdict panel and matrix', async (verdict) => {
    const result =
      verdict === 'INSUFFICIENT_DATA'
        ? insufficient([], { eligibility: { eligible: true, reasons: [] }, agents_degraded: ['news', 'macro'] })
        : withVerdict(verdict, { data_as_of: '2026-08-10', data_age_sessions: 0 })
    arrangeApi(async () => result)
    const { container } = renderApp()
    await selectRow(/^TCB/)
    await analyse()
    await screen.findByText(LABELS[verdict])

    // The disclaimers hold the words by design; the agents' own text is written to avoid them.
    const text = withoutDisclaimers(container.textContent)
    for (const guard of GUARDS) expect(text).not.toMatch(guard)
  })

  it('also holds for every state of the page, not only for results', async () => {
    for (const name of Object.keys(STATES)) {
      arrangeApi(STATES[name].run)
      const { container, unmount } = renderApp()
      await STATES[name].reach()
      const text = withoutDisclaimers(container.textContent)
      for (const guard of GUARDS) expect(text, `${name} ${guard}`).not.toMatch(guard)
      unmount()
      vi.restoreAllMocks()
    }
  })
})
