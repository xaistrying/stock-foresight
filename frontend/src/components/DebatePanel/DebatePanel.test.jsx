import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Top-level mock — hoisted by Vitest before any imports
vi.mock('../../hooks/useDebateAnalysis')

import { DebatePanel } from './DebatePanel'
import { useDebateAnalysis } from '../../hooks/useDebateAnalysis'

const MOCK_RESULT = {
  ticker: 'VCB',
  as_of: '2026-10-04',
  verdict: 'BUY_SIGNAL',
  agreement_level: 'majority',
  round1: {
    technical: { agent_id: 'technical', stance: 'bull', reasoning: ['RSI at 62 is bullish', 'MACD positive'], volatility_range_pct: 1.85 },
    news:      { agent_id: 'news',      stance: 'bull', reasoning: ['Positive Q3 earnings reported'],        volatility_range_pct: null },
    macro:     { agent_id: 'macro',     stance: 'neutral', reasoning: ['VN-Index flat over 20 sessions'],   volatility_range_pct: null },
  },
  round2: {
    technical: { agent_id: 'technical', stance: 'bull', reasoning: ['Maintained — RSI still above 55'], volatility_range_pct: 1.85 },
    news:      { agent_id: 'news',      stance: 'bull', reasoning: ['Held — earnings confirmed'],        volatility_range_pct: null },
    macro:     { agent_id: 'macro',     stance: 'neutral', reasoning: ['Held — macro mixed'],           volatility_range_pct: null },
  },
  synthesis: {
    verdict: 'BUY_SIGNAL',
    agreement_level: 'majority',
    key_tension: 'Technical and news are bullish but macro remains cautious.',
    reasoning: 'Two of three agents signal a bullish picture for VCB.',
  },
  volatility_range_pct: 1.85,
  duration_ms: 4200,
}

function defaultMutation(overrides = {}) {
  return {
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    data: null,
    error: null,
    ...overrides,
  }
}

function renderPanel(ticker = 'VCB') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DebatePanel ticker={ticker} />
    </QueryClientProvider>
  )
}

describe('DebatePanel', () => {
  beforeEach(() => {
    vi.mocked(useDebateAnalysis).mockReturnValue(defaultMutation())
  })

  it('not-run state: shows Analyse button and disclaimer', () => {
    renderPanel()

    expect(screen.getByRole('button', { name: /analyse vcb/i })).toBeInTheDocument()
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })

  it('Level 1: shows verdict and agreement after successful analysis', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(
      defaultMutation({ isSuccess: true, data: MOCK_RESULT })
    )

    renderPanel()

    expect(screen.getByText('Buy Signal')).toBeInTheDocument()
    expect(screen.getByText(/majority/i)).toBeInTheDocument()
  })

  it('disclaimer is present in all states — not-run, loading, success', () => {
    const states = [
      defaultMutation(),
      defaultMutation({ isPending: true }),
      defaultMutation({ isSuccess: true, data: MOCK_RESULT }),
    ]

    for (const state of states) {
      vi.mocked(useDebateAnalysis).mockReturnValue(state)
      const qc = new QueryClient()
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <DebatePanel ticker="VCB" />
        </QueryClientProvider>
      )
      expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
      unmount()
    }
  })

  it('Level 2: agent cards use correct labels', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(
      defaultMutation({ isSuccess: true, data: MOCK_RESULT })
    )

    renderPanel()

    // Expand to Level 2
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

    expect(screen.getAllByText(/Technical Signal/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/News Context/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Macro/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Market Sentiment/)).not.toBeInTheDocument()
  })

  it('"Market Sentiment" label never appears', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(
      defaultMutation({ isSuccess: true, data: MOCK_RESULT })
    )

    renderPanel()

    // Expand all levels
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    fireEvent.click(screen.getByRole('button', { name: /full debate/i }))

    expect(screen.queryByText(/market sentiment/i)).not.toBeInTheDocument()
  })
})
