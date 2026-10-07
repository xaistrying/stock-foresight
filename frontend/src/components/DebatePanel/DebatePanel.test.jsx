import { act, render, screen, fireEvent, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Top-level mocks — hoisted by Vitest before any imports
vi.mock('../../hooks/useDebateAnalysis')
vi.mock('../../hooks/useDebateProgress')

import { DebatePanel } from './DebatePanel'
import { useDebateAnalysis } from '../../hooks/useDebateAnalysis'
import { useDebateProgress } from '../../hooks/useDebateProgress'
import { ApiError } from '../../api/client'
import { FULL_DISCLAIMER, INLINE_DISCLAIMER } from '../../lib/disclaimer'

const MOCK_RESULT = {
  ticker: 'VCB',
  as_of: '2026-10-04',
  verdict: 'BUY_SIGNAL',
  agreement_level: 'majority',
  round1: {
    technical: { agent_id: 'technical', stance: 'bull', reasoning: ['RSI at 62 is bullish', 'MACD positive'], range_5s_pct: 4.14, sigma_daily_pct: 1.85, range_coverage: 0.68 },
    news:      { agent_id: 'news',      stance: 'bull', reasoning: ['Positive Q3 earnings reported'],        range_5s_pct: null, sigma_daily_pct: null, range_coverage: null },
    macro:     { agent_id: 'macro',     stance: 'neutral', reasoning: ['VN-Index flat over 20 sessions'],   range_5s_pct: null, sigma_daily_pct: null, range_coverage: null },
  },
  round2: {
    technical: { agent_id: 'technical', stance: 'bull', reasoning: ['Maintained — RSI still above 55'], range_5s_pct: 4.14, sigma_daily_pct: 1.85, range_coverage: 0.68 },
    news:      { agent_id: 'news',      stance: 'bull', reasoning: ['Held — earnings confirmed'],        range_5s_pct: null, sigma_daily_pct: null, range_coverage: null },
    macro:     { agent_id: 'macro',     stance: 'neutral', reasoning: ['Held — macro mixed'],           range_5s_pct: null, sigma_daily_pct: null, range_coverage: null },
  },
  synthesis: {
    verdict: 'BUY_SIGNAL',
    agreement_level: 'majority',
    key_tension: 'Technical and news are bullish but macro remains cautious.',
    reasoning: 'Two of three agents signal a bullish picture for VCB.',
  },
  range_5s_pct: 4.14,
  sigma_daily_pct: 1.85,
  range_coverage: 0.68,
  duration_ms: 4200,
}

// What useDebateAnalysis returns (the panel never sees the mutation behind it).
const DONE_AT = new Date(2026, 9, 7, 14, 32).getTime() // local time: "Analysed 14:32"

function analysis(overrides = {}) {
  return {
    analyse: vi.fn(),
    isPending: false,
    startedAt: null,
    result: null,
    completedAt: null,
    error: null,
    ...overrides,
  }
}

const finished = (result) => analysis({ result, completedAt: DONE_AT })
const running = (overrides = {}) => analysis({ isPending: true, startedAt: Date.now(), ...overrides })

function renderPanel(ticker = 'VCB') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DebatePanel ticker={ticker} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.mocked(useDebateAnalysis).mockReturnValue(analysis())
  vi.mocked(useDebateProgress).mockReturnValue({ data: undefined })
})

describe('DebatePanel', () => {
  it('not-run state: shows Analyse button and disclaimer', () => {
    renderPanel()

    expect(screen.getByRole('button', { name: /analyse vcb/i })).toBeInTheDocument()
    expect(screen.getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
  })

  it('Level 1: shows verdict and agreement after successful analysis', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(finished(MOCK_RESULT))

    renderPanel()

    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(screen.getByText(/majority/i)).toBeInTheDocument()
  })

  it('disclaimer is present in all states — not-run, loading, success', () => {
    const states = [analysis(), running(), finished(MOCK_RESULT)]

    for (const state of states) {
      vi.mocked(useDebateAnalysis).mockReturnValue(state)
      const qc = new QueryClient()
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <DebatePanel ticker="VCB" />
        </QueryClientProvider>
      )
      expect(screen.getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
      unmount()
    }
  })

  it('Level 2: agent cards use correct labels', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(finished(MOCK_RESULT))

    renderPanel()

    // Expand to Level 2
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

    expect(screen.getAllByText(/Technical Signal/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/News Context/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Macro/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Market Sentiment/)).not.toBeInTheDocument()
  })

  it('"Market Sentiment" label never appears', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(finished(MOCK_RESULT))

    renderPanel()

    // Expand all levels
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    fireEvent.click(screen.getByRole('button', { name: /full debate/i }))

    expect(screen.queryByText(/market sentiment/i)).not.toBeInTheDocument()
  })
})


// ------------------------------------------------------------------ //
// debate-data-guards: data date, degraded agents, insufficient data
// ------------------------------------------------------------------ //

const DISCLAIMER = INLINE_DISCLAIMER

const position = (agentId, stance, reasoning, extra = {}) => ({
  agent_id: agentId, stance, reasoning, range_5s_pct: null, sigma_daily_pct: null, range_coverage: null, degraded_reason: null, ...extra,
})

const NEWS_DEGRADED = position('news', 'neutral', ['PLACEHOLDER news'], { degraded_reason: 'llm_failed' })

function populated(overrides = {}) {
  return {
    ...MOCK_RESULT,
    data_as_of: '2026-10-02',
    data_age_sessions: 2,
    eligibility: { eligible: true, reasons: [] },
    agents_degraded: [],
    ...overrides,
  }
}

function insufficient(reasons, overrides = {}) {
  return {
    ticker: 'VCB',
    as_of: '2026-09-07',
    data_as_of: '2026-09-07',
    data_age_sessions: 21,
    verdict: 'INSUFFICIENT_DATA',
    agreement_level: 'none',
    eligibility: { eligible: false, reasons },
    agents_degraded: [],
    round1: {},
    round2: {},
    synthesis: { verdict: 'INSUFFICIENT_DATA', agreement_level: 'none', key_tension: '', reasoning: '' },
    range_5s_pct: null,
    sigma_daily_pct: null,
    range_coverage: null,
    duration_ms: 0,
    ...overrides,
  }
}

function show(data) {
  vi.mocked(useDebateAnalysis).mockReturnValue(finished(data))
  return renderPanel()
}

describe('DebatePanel — data date and degraded agents', () => {
  it('Level 1 shows the data date and its age in sessions without expanding anything', () => {
    show(populated({ data_as_of: '2026-10-02', data_age_sessions: 2 }))

    expect(screen.getByText('Data as of 2026-10-02 · 2 sessions old')).toBeInTheDocument()
  })

  it('reads "current" at age 0 and "1 session old" at age 1', () => {
    const { unmount } = show(populated({ data_age_sessions: 0 }))
    expect(screen.getByText('Data as of 2026-10-02 · current')).toBeInTheDocument()
    unmount()

    show(populated({ data_age_sessions: 1 }))
    expect(screen.getByText('Data as of 2026-10-02 · 1 session old')).toBeInTheDocument()
  })

  it('a payload without data fields (an older server) still renders, with no data line', () => {
    show(MOCK_RESULT)

    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(screen.queryByText(/data as of/i)).not.toBeInTheDocument()
  })

  describe('one degraded agent', () => {
    const oneDegraded = () => populated({
      round1: { ...MOCK_RESULT.round1, news: NEWS_DEGRADED },
      round2: {
        technical: position('technical', 'bull', ['RSI above 55']),
        news: NEWS_DEGRADED,
        macro: position('macro', 'bull', ['VN-Index up']),
      },
      agents_degraded: ['news'],
    })

    it('marks the agent unavailable in the stance row (text and icon) and counts live agents only', () => {
      show(oneDegraded())

      expect(screen.getByText(/News Context ⚠ unavailable/)).toBeInTheDocument()
      expect(screen.getByText('Agreement: 2 of 2 live agents (1 unavailable)')).toBeInTheDocument()
      expect(screen.queryByText(/unanimous/i)).not.toBeInTheDocument()
    })

    it('Level 2 gives the plain-language reason on the agent card', () => {
      show(oneDegraded())
      fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

      expect(screen.getByText('The language-model analysis failed.')).toBeInTheDocument()
    })

    it('a split of two live agents reads "Split — 2 different positions"', () => {
      show({
        ...oneDegraded(),
        verdict: 'SPLIT',
        agreement_level: 'split',
        round2: {
          technical: position('technical', 'bull', ['RSI above 55']),
          news: NEWS_DEGRADED,
          macro: position('macro', 'neutral', ['VN-Index flat']),
        },
      })

      expect(screen.getByText(/Split — 2 different positions/)).toBeInTheDocument()
    })
  })

  it('a Round 2 failure shows the Round 1 position under its "not counted" marker', () => {
    const failed = position('technical', 'bull', ['RSI high', 'Round 2 unavailable — Round 1 position kept, not counted in the vote.'], {
      degraded_reason: 'round2_failed',
    })
    show(populated({
      round2: { ...MOCK_RESULT.round2, technical: failed },
      agents_degraded: ['technical'],
    }))
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

    expect(screen.getByText('Round 2 failed; its Round 1 position is shown but not counted.')).toBeInTheDocument()
    expect(screen.getByText('RSI high')).toBeInTheDocument()
  })

  it('Level 1 with no degraded agent keeps the three-agent agreement text', () => {
    show(populated())

    expect(screen.getByText('Agreement: Majority — 2 of 3 agents')).toBeInTheDocument()
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument()
  })
})

describe('DebatePanel — insufficient data', () => {
  it('stale: states the reason with the age, points at Refresh, and shows no verdict detail', () => {
    show(insufficient(['stale']))

    expect(screen.getByText('Insufficient data')).toBeInTheDocument()
    expect(screen.getByText('Data as of 2026-09-07 · 21 sessions old')).toBeInTheDocument()
    expect(
      screen.getByText('Stored prices are 21 sessions old. Refresh the ticker in the ticker panel, then analyse again.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Technical Signal/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /show reasoning/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/typical 5-session move:/i)).not.toBeInTheDocument()
  })

  it('keeps the disclaimer and Re-analyse, and shows no report-saved note', () => {
    show(insufficient(['stale']))

    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-analyse vcb/i })).toBeInTheDocument()
    expect(screen.queryByText(/report saved/i)).not.toBeInTheDocument()
  })

  it('lists one sentence per reason, in the order given', () => {
    show(insufficient(['delisted', 'stale', 'hard_quality_flag']))

    expect(screen.getAllByRole('listitem').map(li => li.textContent)).toEqual([
      'This ticker is delisted.',
      'Stored prices are 21 sessions old. Refresh the ticker in the ticker panel, then analyse again.',
      'A recent price failed a data-quality check.',
    ])
  })

  it.each([
    ['insufficient_history', 'Not enough price history (at least 65 sessions are needed).'],
    ['near_gap', 'The price history has missing sessions.'],
    ['indicators_missing', 'Technical indicators are not available for the latest session.'],
  ])('%s has its own sentence', (reason, sentence) => {
    show(insufficient([reason]))

    expect(screen.getByText(sentence)).toBeInTheDocument()
  })

  it('with no reasons and two degraded agents, lists each agent and says why it abstained', () => {
    const news = position('news', 'neutral', ['x'], { degraded_reason: 'no_input' })
    const macro = position('macro', 'neutral', ['x'], { degraded_reason: 'agent_error' })
    const technical = position('technical', 'bull', ['RSI high'])
    show(insufficient([], {
      eligibility: { eligible: true, reasons: [] },
      data_age_sessions: 1,
      agents_degraded: ['news', 'macro'],
      round1: { technical, news, macro },
      round2: { technical, news, macro },
    }))

    expect(screen.getByText(/fewer than two agents produced a usable position/i)).toBeInTheDocument()
    expect(screen.getByText(/News Context.*No usable input data\./)).toBeInTheDocument()
    expect(screen.getByText(/Macro.*The agent failed to run\./)).toBeInTheDocument()
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument()
  })

  it('never uses the "Market Sentiment" label (Rule 5) in any of the new states', () => {
    const { unmount } = show(insufficient(['stale']))
    expect(screen.queryByText(/market sentiment/i)).not.toBeInTheDocument()
    unmount()

    show(populated({ round2: { ...MOCK_RESULT.round2, news: NEWS_DEGRADED }, agents_degraded: ['news'] }))
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    expect(screen.queryByText(/market sentiment/i)).not.toBeInTheDocument()
  })
})


// ------------------------------------------------------------------ //
// align-rules-and-disclaimer: labels, Agreement, LM note, disclaimer
// ------------------------------------------------------------------ //

const LABELS = {
  STRONG_BUY_SIGNAL: 'Strong bullish lean',
  BUY_SIGNAL: 'Bullish lean',
  OBSERVE: 'Observe',
  CAUTION_SIGNAL: 'Bearish lean',
  STRONG_CAUTION_SIGNAL: 'Strong bearish lean',
  SPLIT: 'Split — no consensus',
}
const LM_NOTE = 'Reasoning, key tension and synthesis are written by a language model.'

function withVerdict(verdict, extra = {}) {
  return populated({
    verdict,
    synthesis: { ...MOCK_RESULT.synthesis, verdict },
    ...extra,
  })
}

describe('DebatePanel — verdict labels and Agreement', () => {
  it.each(Object.entries(LABELS))('%s renders "%s"', (verdict, label) => {
    show(withVerdict(verdict))

    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('INSUFFICIENT_DATA renders "Insufficient data"', () => {
    show(insufficient(['stale']))

    expect(screen.getByText('Insufficient data')).toBeInTheDocument()
  })

  it('an unknown verdict renders "Unrecognised verdict", never the enum', () => {
    show(withVerdict('SOMETHING_NEW'))

    expect(screen.getByText('Unrecognised verdict')).toBeInTheDocument()
    expect(screen.queryByText(/SOMETHING_NEW/)).not.toBeInTheDocument()
  })

  it('a split reads "Agreement: Split — 3 different positions"', () => {
    show(withVerdict('SPLIT', {
      agreement_level: 'split',
      round2: {
        technical: position('technical', 'bull', ['a']),
        news: position('news', 'neutral', ['b']),
        macro: position('macro', 'bear', ['c']),
      },
    }))

    expect(screen.getByText('Agreement: Split — 3 different positions')).toBeInTheDocument()
  })
})

describe('DebatePanel — language-model note', () => {
  it('shows the note at Level 2 and again at Level 3', () => {
    show(populated())
    expect(screen.queryByText(LM_NOTE)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    expect(screen.getAllByText(LM_NOTE)).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: /full debate/i }))
    expect(screen.getAllByText(LM_NOTE)).toHaveLength(2)
  })
})

describe('DebatePanel — disclaimer', () => {
  const STATES = {
    'not-run': () => analysis(),
    loading: () => running(),
    error: () => analysis({ error: new Error('boom') }),
    populated: () => finished(populated()),
    insufficient: () => finished(insufficient(['stale'])),
  }

  it.each(Object.keys(STATES))('%s: inline text visible, full text inside "About this analysis"', name => {
    vi.mocked(useDebateAnalysis).mockReturnValue(STATES[name]())
    renderPanel()

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
    const details = screen.getByText('About this analysis').closest('details')
    expect(details).toHaveTextContent(FULL_DISCLAIMER)
    expect(details).not.toContainElement(screen.getByText(INLINE_DISCLAIMER))
  })

  it('opening the disclosure keeps the inline text visible', () => {
    renderPanel()

    fireEvent.click(screen.getByText('About this analysis'))

    expect(screen.getByText('About this analysis').closest('details')).toHaveAttribute('open')
    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
  })

  it('shows no repo path', () => {
    renderPanel()

    expect(screen.queryByText(/DISCLAIMER\.md/)).not.toBeInTheDocument()
  })
})

describe('DebatePanel — fixed text has no transaction verbs, enum text or Confidence', () => {
  const GUARDS = [/\b(buy|sell|hold)\b/i, /[A-Z]+_SIGNAL\b|INSUFFICIENT_DATA/, /\bconfiden(ce|t)\b/i, /market sentiment/i]

  function expectClean(container) {
    const text = container.textContent.replace(INLINE_DISCLAIMER, '').replace(FULL_DISCLAIMER, '')
    for (const guard of GUARDS) expect(text).not.toMatch(guard)
  }

  it.each([
    ['not-run', () => analysis()],
    ['loading', () => running()],
    ['error', () => analysis({ error: new Error('boom') })],
  ])('%s state', (_name, make) => {
    vi.mocked(useDebateAnalysis).mockReturnValue(make())
    const { container } = renderPanel()

    expectClean(container)
  })

  it.each([...Object.keys(LABELS), 'INSUFFICIENT_DATA'])('%s at Levels 1 to 3', verdict => {
    const data = verdict === 'INSUFFICIENT_DATA' ? insufficient(['stale']) : withVerdict(verdict)
    const { container } = show(data)
    expectClean(container)

    if (verdict === 'INSUFFICIENT_DATA') return
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    expectClean(container)
    fireEvent.click(screen.getByRole('button', { name: /full debate/i }))
    expectClean(container)
  })
})


// ------------------------------------------------------------------ //
// calibrate-volatility-range: the typical 5-session move and its coverage
// ------------------------------------------------------------------ //

const RANGE_LINE = /Typical 5-session move:/

describe('DebatePanel — typical 5-session move', () => {
  it('shows the band with its coverage as "about 2 in 3" at a nominal 0.68', () => {
    show(populated({ range_5s_pct: 5.3, range_coverage: 0.68 }))

    expect(
      screen.getByText('Typical 5-session move: ±5.3% (about 2 in 3 recent 5-session moves stayed within this range)'),
    ).toBeInTheDocument()
  })

  it('renders one decimal and phrases any other coverage as the nearest 5 percent', () => {
    show(populated({ range_5s_pct: 5.26, range_coverage: 0.8 }))

    expect(
      screen.getByText('Typical 5-session move: ±5.3% (about 80% recent 5-session moves stayed within this range)'),
    ).toBeInTheDocument()
  })

  it('rounds an unusual coverage to the nearest 5 percent', () => {
    show(populated({ range_5s_pct: 5.3, range_coverage: 0.9 }))

    expect(screen.getByText(/about 90% recent 5-session moves/)).toBeInTheDocument()
  })

  it('claims no coverage for a stock it was not measured on', () => {
    show(populated({ range_5s_pct: 5.3, range_coverage: null }))

    expect(
      screen.getByText('Typical 5-session move: ±5.3% (coverage not established for this stock)'),
    ).toBeInTheDocument()
    // the Rule 6 disclaimer, not this line's to edit, carries its own 2-in-3 wording
    expect(screen.getByText(RANGE_LINE).textContent).not.toMatch(/2 in 3/)
  })

  it('renders no line and no placeholder when no band was served', () => {
    show(populated({ range_5s_pct: null, sigma_daily_pct: null, range_coverage: null }))

    expect(screen.queryByText(RANGE_LINE)).not.toBeInTheDocument()
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument()
  })

  it('never uses "expected", "confidence" or "forecast" and never shows the daily sigma', () => {
    show(populated({ range_5s_pct: 5.3, sigma_daily_pct: 1.77, range_coverage: 0.68 }))

    const line = screen.getByText(RANGE_LINE)
    expect(line.textContent).not.toMatch(/expected|confidence|forecast/i)
    expect(screen.queryByText(/1\.77/)).not.toBeInTheDocument()
  })

  it('sits in the panel that carries the Rule 6 disclaimer', () => {
    show(populated({ range_5s_pct: 5.3, range_coverage: 0.68 }))

    expect(screen.getByText(RANGE_LINE)).toBeInTheDocument()
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument()
  })
})


// ------------------------------------------------------------------ //
// harden-debate-runtime: running stage, kept result, failure reasons
// ------------------------------------------------------------------ //

const ROUND2 = { ticker: 'VCB', running: true, stage: 'round2', elapsed_ms: 8000 }

// The panel's hooks are mocked, so it needs no QueryClientProvider here.
const mountPanel = (ticker = 'VCB') => render(<DebatePanel ticker={ticker} />)

describe('DebatePanel — running stage and elapsed time', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it.each([
    ['round1', 'Running agents…'],
    ['round2', 'Comparing positions…'],
    ['synthesis', 'Synthesising…'],
  ])('shows the server stage "%s" as "%s"', (stage, label) => {
    vi.mocked(useDebateAnalysis).mockReturnValue(running())
    vi.mocked(useDebateProgress).mockReturnValue({ data: { ...ROUND2, stage } })

    mountPanel()

    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it.each([
    ['before the first poll has answered', undefined],
    ['when the server reports no stage', { ticker: 'VCB', running: false, stage: null, elapsed_ms: null }],
  ])('says "Running agents…" %s', (_when, data) => {
    vi.mocked(useDebateAnalysis).mockReturnValue(running())
    vi.mocked(useDebateProgress).mockReturnValue({ data })

    mountPanel()

    expect(screen.getByText('Running agents…')).toBeInTheDocument()
  })

  it('polls for the ticker and the start time of the run that is pending', () => {
    const startedAt = Date.now() - 3000
    vi.mocked(useDebateAnalysis).mockReturnValue(running({ startedAt }))

    mountPanel('VCB')

    expect(useDebateProgress).toHaveBeenCalledWith('VCB', startedAt)
  })

  it('counts the elapsed seconds since the request was submitted', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 7, 10, 0, 0))
    vi.mocked(useDebateAnalysis).mockReturnValue(running({ startedAt: Date.now() }))

    mountPanel()
    expect(screen.getByText('0 s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(12_000)
    })

    expect(screen.getByText('12 s')).toBeInTheDocument()
  })

  it('shows the time already spent when it returns to a run that began earlier', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 7, 10, 0, 30))
    vi.mocked(useDebateAnalysis).mockReturnValue(running({ startedAt: new Date(2026, 9, 7, 10, 0, 0).getTime() }))

    mountPanel()

    expect(screen.getByText('30 s')).toBeInTheDocument()
  })

  it('keeps the last label and shows no error when a progress poll fails', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(running())
    vi.mocked(useDebateProgress).mockReturnValue({ data: ROUND2 })
    const { rerender } = mountPanel()
    expect(screen.getByText('Comparing positions…')).toBeInTheDocument()

    vi.mocked(useDebateProgress).mockReturnValue({ data: ROUND2, isError: true, error: new Error('network') })
    rerender(<DebatePanel ticker="VCB" />)

    expect(screen.getByText('Comparing positions…')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('offers no Analyse or Retry button while a run is going, so it cannot be started twice', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(running())

    mountPanel()

    expect(screen.queryByRole('button', { name: /analyse|retry/i })).not.toBeInTheDocument()
  })

  it('keeps the disclaimer in view while running', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(running())

    mountPanel()

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
  })
})

describe('DebatePanel — the kept result and its time', () => {
  it('labels a result with the time it was produced', () => {
    show(populated())

    expect(screen.getByText('Analysed 14:32')).toBeInTheDocument()
  })

  it('shows each ticker\'s kept result from its own state, without a new request, after switching away and back', () => {
    const states = { VCB: finished(populated()), FPT: analysis() }
    vi.mocked(useDebateAnalysis).mockImplementation((ticker) => states[ticker])

    const vcb = mountPanel('VCB')
    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    vcb.unmount()

    const fpt = mountPanel('FPT') // never analysed this session
    expect(screen.getByRole('button', { name: /analyse fpt/i })).toBeInTheDocument()
    expect(screen.queryByText('Bullish lean')).not.toBeInTheDocument()
    fpt.unmount()

    mountPanel('VCB')
    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(states.VCB.analyse).not.toHaveBeenCalled()
  })

  it('shows the running state, not the old result as if current, while a re-run is going', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(running({ result: populated(), completedAt: DONE_AT }))

    mountPanel()

    expect(screen.getByText('Running agents…')).toBeInTheDocument()
    expect(screen.queryByText('Bullish lean')).not.toBeInTheDocument()
  })

  it('keeps the old result when a re-run fails, with the error shown above it', () => {
    const error = new ApiError('boom', { status: 500, body: { detail: 'boom' } })
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ result: populated(), completedAt: DONE_AT, error }))

    mountPanel()

    const alert = screen.getByRole('alert')
    const verdict = screen.getByText('Bullish lean')
    expect(alert.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('Analysed 14:32')).toBeInTheDocument()
  })

  it('starts a run from the Analyse button', () => {
    const state = analysis()
    vi.mocked(useDebateAnalysis).mockReturnValue(state)
    mountPanel()

    fireEvent.click(screen.getByRole('button', { name: /analyse vcb/i }))

    expect(state.analyse).toHaveBeenCalledTimes(1)
  })
})

const busy = () => new ApiError('Another analysis is already running; try again shortly.', {
  status: 429, body: { detail: 'Another analysis is already running; try again shortly.', code: 'debate_busy' },
})
const notConfigured = () => new ApiError('DEBATE_LLM_EFFORT is not valid. Supported: low, medium, high.', {
  status: 503, body: { detail: 'DEBATE_LLM_EFFORT is not valid. Supported: low, medium, high.', code: 'debate_not_configured' },
})
const serverTimeout = () => new ApiError('The analysis did not finish within 180 s.', {
  status: 504, body: { detail: 'The analysis did not finish within 180 s.', code: 'debate_timeout' },
})
const clientTimeout = () => new ApiError('The request timed out.', { timedOut: true })
const notLoaded = () => new ApiError('Ticker has not been loaded', { status: 404, body: { detail: 'Ticker has not been loaded' } })
const serverFailure = () => new ApiError('database is locked', { status: 500, body: { detail: 'database is locked' } })
const unreachable = () => new ApiError('Network error — could not reach the server.')

describe('DebatePanel — why an analysis could not run', () => {
  const MESSAGES = [
    ['not loaded (404)', notLoaded, "VCB hasn't been loaded yet. Load it from the ticker panel first."],
    // (its button is covered by the test below)
    ['busy (429)', busy, 'Another analysis is already running; try again shortly.'],
    ['not configured (503), with the server\'s message', notConfigured, 'DEBATE_LLM_EFFORT is not valid. Supported: low, medium, high.'],
    ['server timeout (504)', serverTimeout, /timed out on the server/i],
    ['client time limit', clientTimeout, 'No answer after 200 s. The server may still be working; Analyse again to rejoin it.'],
    ['any other failure, with the server\'s detail', serverFailure, 'database is locked'],
    ['a network failure', unreachable, 'Network error — could not reach the server.'],
  ]

  it.each(MESSAGES)('%s says why', (_name, make, message) => {
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error: make() }))

    mountPanel()

    expect(within(screen.getByRole('alert')).getByText(message)).toBeInTheDocument()
  })

  it.each(MESSAGES)('%s keeps the disclaimer visible', (_name, make) => {
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error: make() }))

    mountPanel()

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
    expect(screen.getByText('About this analysis').closest('details')).toHaveTextContent(FULL_DISCLAIMER)
  })

  it('any other failure also says the generic sentence, and a plain Error shows only that', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error: serverFailure() }))
    const first = mountPanel()
    expect(screen.getByText('Analysis failed — please try again.')).toBeInTheDocument()
    first.unmount()

    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error: new Error('boom') }))
    mountPanel()
    expect(screen.getByText('Analysis failed — please try again.')).toBeInTheDocument()
    expect(screen.queryByText('boom')).not.toBeInTheDocument()
  })

  it('the client time limit is not described as an unreachable server', () => {
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error: clientTimeout() }))

    mountPanel()

    expect(screen.queryByText(/could not reach the server/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyse again' })).toBeInTheDocument()
  })

  it.each([
    ['busy (429)', busy, 'Retry'],
    ['not configured (503)', notConfigured, 'Retry'],
    ['server timeout (504)', serverTimeout, 'Retry'],
    ['client time limit', clientTimeout, 'Analyse again'],
    ['any other failure', serverFailure, 'Retry'],
  ])('%s offers "%s", which starts a run', (_name, make, label) => {
    const state = analysis({ error: make() })
    vi.mocked(useDebateAnalysis).mockReturnValue(state)
    mountPanel()

    fireEvent.click(screen.getByRole('button', { name: label }))

    expect(state.analyse).toHaveBeenCalledTimes(1)
  })

  it('not loaded still offers a way to run again: the error survives a remount, so it must not be a dead end', () => {
    const state = analysis({ error: notLoaded() })
    vi.mocked(useDebateAnalysis).mockReturnValue(state)

    mountPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Analyse again' }))

    expect(state.analyse).toHaveBeenCalledTimes(1)
  })

  it('a structured detail (not a string) is ignored instead of crashing the panel', () => {
    const error = new ApiError('x', { status: 422, body: { detail: [{ loc: ['path'], msg: 'bad' }] } })
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error }))

    mountPanel()

    expect(screen.getByText('Analysis failed — please try again.')).toBeInTheDocument()
  })

  it.each(MESSAGES)('%s uses no transaction verb, enum text, Confidence or Market Sentiment', (_name, make) => {
    vi.mocked(useDebateAnalysis).mockReturnValue(analysis({ error: make() }))

    const { container } = mountPanel()

    const text = container.textContent.replace(INLINE_DISCLAIMER, '').replace(FULL_DISCLAIMER, '')
    for (const guard of [/\b(buy|sell|hold)\b/i, /[A-Z]+_SIGNAL\b|INSUFFICIENT_DATA/, /\bconfiden(ce|t)\b/i, /market sentiment/i]) {
      expect(text).not.toMatch(guard)
    }
  })
})

describe('DebatePanel — the report line', () => {
  function openFullDebate() {
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    fireEvent.click(screen.getByRole('button', { name: /full debate/i }))
  }

  it('says where the report was saved, with the file name the server returned, when it was saved', () => {
    show(populated({ report_saved: true, report_file: '2026-10-05_VPB.md' }))
    openFullDebate()

    expect(screen.getByText(/report saved to/i)).toHaveTextContent('Report saved to reports/2026-10-05_VPB.md')
  })

  it('does not guess the file name from the date and ticker', () => {
    show(populated({ report_saved: true, report_file: 'a-different-name.md', as_of: '2026-10-04' }))
    openFullDebate()

    expect(screen.getByText(/report saved to/i)).toHaveTextContent('reports/a-different-name.md')
    expect(screen.queryByText(/2026-10-04_VCB/)).not.toBeInTheDocument()
  })

  it.each([
    ['false', { report_saved: false, report_file: null }],
    ['absent (an older server)', {}],
    ['true without a file name', { report_saved: true, report_file: null }],
  ])('claims nothing when report_saved is %s', (_name, fields) => {
    show(populated(fields))
    openFullDebate()

    expect(screen.queryByText(/report saved/i)).not.toBeInTheDocument()
  })
})

describe('DebatePanel — Markdown bold in model text', () => {
  const withBold = () => populated({
    round2: {
      ...MOCK_RESULT.round2,
      technical: position('technical', 'bull', ['**RSI at 39.6** is below the midpoint, **and** momentum is weak']),
    },
    synthesis: { ...MOCK_RESULT.synthesis, key_tension: 'The **key point** is the index.', reasoning: 'A **bold** summary.' },
  })

  it('renders **text** as bold and shows no asterisks, in bullets, key tension and synthesis', () => {
    const { container } = show(withBold())
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))
    fireEvent.click(screen.getByRole('button', { name: /full debate/i }))

    expect(container.textContent).not.toContain('**')
    expect(screen.getAllByText('RSI at 39.6')[0].tagName).toBe('STRONG')
    expect(screen.getByText('key point').tagName).toBe('STRONG')
    expect(screen.getByText('bold').tagName).toBe('STRONG')
  })

  it('leaves a lone or unmatched asterisk alone and never treats text as HTML', () => {
    show(populated({
      round2: { ...MOCK_RESULT.round2, technical: position('technical', 'bull', ['5 * 3 and **unclosed', '<b>not bold</b>']) },
    }))
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

    expect(screen.getByText('5 * 3 and **unclosed')).toBeInTheDocument()
    expect(screen.getByText('<b>not bold</b>')).toBeInTheDocument()
  })
})

describe('DebatePanel — an unavailable key tension', () => {
  const keyTensionBlock = () => screen.getByText('Key Tension').closest('div')

  it('says so under the Key Tension heading and shows no text as the key tension', () => {
    show(populated({ synthesis: { ...MOCK_RESULT.synthesis, key_tension: null } }))
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

    expect(within(keyTensionBlock()).getByText('Key tension unavailable')).toBeInTheDocument()
    expect(within(keyTensionBlock()).queryByText(MOCK_RESULT.synthesis.key_tension)).not.toBeInTheDocument()
  })

  it('still shows a key tension the model wrote', () => {
    show(populated())
    fireEvent.click(screen.getByRole('button', { name: /show reasoning/i }))

    expect(within(keyTensionBlock()).getByText(MOCK_RESULT.synthesis.key_tension)).toBeInTheDocument()
    expect(screen.queryByText(/key tension unavailable/i)).not.toBeInTheDocument()
  })
})
