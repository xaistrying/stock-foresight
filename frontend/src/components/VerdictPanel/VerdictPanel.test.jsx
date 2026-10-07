import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The panel reads its run from props (useDebateAnalysis is called once, in the workspace), the
// server's stage from the progress hook and what it knows about the ticker from the context hook;
// the last two are mocked so every state can be set up directly.
vi.mock('../../hooks/useDebateProgress')
vi.mock('../../hooks/useTickerContext')

import { VerdictPanel } from './VerdictPanel'
import { useDebateProgress } from '../../hooks/useDebateProgress'
import { useTickerContext } from '../../hooks/useTickerContext'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { FULL_DISCLAIMER, INLINE_DISCLAIMER, LM_NOTE } from '../../lib/disclaimer'
import { readSrc, rulesFor, parseRules, declarations } from '../../test/cssText'
import { newQueryClient, renderWithQuery } from '../../test/railFixtures'
import {
  DONE_AT, FORBIDDEN_TEXT, LABELS, MOCK_RESULT, NEWS_DEGRADED, analysisState, insufficient, oneDegraded,
  populated, position, withVerdict,
} from '../../test/debateFixtures'

const context = (overrides = {}) => ({
  asOf: '2026-10-06',
  ageSessions: 0,
  stale: false,
  reasons: [],
  eligible: true,
  lastClose: 42.55,
  ...overrides,
})
const STALE_CONTEXT = context({ asOf: '2026-09-07', ageSessions: 21, stale: true, reasons: ['stale'], eligible: false })

const finished = (result) => analysisState({ result, completedAt: DONE_AT })
const running = (overrides = {}) => analysisState({ isPending: true, startedAt: Date.now(), ...overrides })

function renderPanel(analysis = analysisState(), { ticker = 'VCB', ...props } = {}) {
  return renderWithQuery(<VerdictPanel ticker={ticker} analysis={analysis} showRange={false} {...props} />)
}
const show = (result) => renderPanel(finished(result))

beforeEach(() => {
  vi.restoreAllMocks()
  vi.mocked(useTickerContext).mockReturnValue(context())
  vi.mocked(useDebateProgress).mockReturnValue({ data: undefined })
})

describe('Verdict panel landmark and ticker prompt', () => {
  it('is an aside named Verdict', () => {
    renderPanel()

    expect(screen.getByRole('complementary', { name: 'Verdict' })).toBeInTheDocument()
  })

  it('asks for a ticker when none is selected, and still shows the disclaimer', () => {
    renderPanel(analysisState(), { ticker: null })

    expect(screen.getByText(/select a ticker to run debate analysis/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /analyse/i })).not.toBeInTheDocument()
    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
  })

  it('shows the range block above every state when asked to, and not otherwise', async () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({
      ticker: 'VCB', as_of: '2026-10-06', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
      range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 },
    })
    const first = renderPanel(analysisState(), { showRange: true })
    expect(await screen.findByText('±4.12%')).toBeInTheDocument()
    first.unmount()

    renderPanel(analysisState(), { showRange: false })
    expect(screen.queryByText('Typical 5-session move')).not.toBeInTheDocument()
  })
})

describe('Verdict panel: ready', () => {
  it('offers Analyse and says how long it takes, with no verdict values', () => {
    renderPanel()

    expect(screen.getByRole('button', { name: 'Analyse VCB' })).toBeInTheDocument()
    expect(screen.getByText('Analysis takes about 45 seconds.')).toBeInTheDocument()
    expect(screen.queryByText(/agreement/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/lean|observe|split/i)).not.toBeInTheDocument()
  })

  it('starts a run from the Analyse button', () => {
    const state = analysisState({ analyse: vi.fn() })
    renderPanel(state)

    fireEvent.click(screen.getByRole('button', { name: 'Analyse VCB' }))

    expect(state.analyse).toHaveBeenCalledTimes(1)
  })

  it('keeps the disclaimer visible', () => {
    renderPanel()

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
  })
})

describe('Verdict panel: running', () => {
  afterEach(() => {
    vi.useRealTimers()
  })
  const ROUND2 = { ticker: 'VCB', running: true, stage: 'round2', elapsed_ms: 8000 }

  it.each([
    ['round1', 'Running agents…'],
    ['round2', 'Comparing positions…'],
    ['synthesis', 'Synthesising…'],
  ])('shows the server stage "%s" as "%s"', (stage, label) => {
    vi.mocked(useDebateProgress).mockReturnValue({ data: { ...ROUND2, stage } })

    renderPanel(running())

    expect(screen.getByRole('status')).toHaveTextContent(label)
  })

  it.each([
    ['before the first poll has answered', undefined],
    ['when the server reports no stage', { ticker: 'VCB', running: false, stage: null, elapsed_ms: null }],
  ])('says "Running agents…" %s', (_when, data) => {
    vi.mocked(useDebateProgress).mockReturnValue({ data })

    renderPanel(running())

    expect(screen.getByText('Running agents…')).toBeInTheDocument()
  })

  it('polls for the ticker and the start time of the run that is pending', () => {
    const startedAt = Date.now() - 3000

    renderPanel(running({ startedAt }))

    expect(useDebateProgress).toHaveBeenCalledWith('VCB', startedAt)
  })

  it('counts the elapsed seconds since the request was submitted', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 7, 10, 0, 0))

    renderPanel(running({ startedAt: Date.now() }))
    expect(screen.getByText('0 s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(12_000)
    })

    expect(screen.getByText('12 s')).toBeInTheDocument()
  })

  it('shows the time already spent when it returns to a run that began earlier', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 7, 10, 0, 30))

    renderPanel(running({ startedAt: new Date(2026, 9, 7, 10, 0, 0).getTime() }))

    expect(screen.getByText('30 s')).toBeInTheDocument()
  })

  it('keeps the last label and shows no error when a progress poll fails', () => {
    vi.mocked(useDebateProgress).mockReturnValue({ data: ROUND2 })
    const { rerender, queryClient } = renderPanel(running())
    expect(screen.getByText('Comparing positions…')).toBeInTheDocument()

    vi.mocked(useDebateProgress).mockReturnValue({ data: ROUND2, isError: true, error: new Error('network') })
    rerender(
      <QueryClientProvider client={queryClient}>
        <VerdictPanel ticker="VCB" analysis={running()} showRange={false} />
      </QueryClientProvider>,
    )

    expect(screen.getByText('Comparing positions…')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('offers no Analyse or Retry button while a run is going, so it cannot be started twice', () => {
    renderPanel(running())

    expect(screen.queryByRole('button', { name: /analyse|retry/i })).not.toBeInTheDocument()
  })

  it('shows the running state, never the old result as if it were current, while a re-run is going', () => {
    renderPanel(running({ result: populated(), completedAt: DONE_AT }))

    expect(screen.getByText('Running agents…')).toBeInTheDocument()
    expect(screen.queryByText('Bullish lean')).not.toBeInTheDocument()
  })

  it('keeps the disclaimer in view', () => {
    renderPanel(running())

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
  })
})

describe('Verdict panel: result', () => {
  it('shows the badge, Agreement, three stance chips, Key tension, Synthesis and the data line, all at once', () => {
    show(populated({ data_as_of: '2026-10-02', data_age_sessions: 2 }))

    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(screen.getByText('Agreement: Majority — 2 of 3 agents')).toBeInTheDocument()
    expect(screen.getByText('Technical Signal ↑ Bullish')).toBeInTheDocument()
    expect(screen.getByText('News Context ↑ Bullish')).toBeInTheDocument()
    expect(screen.getByText('Macro → Neutral')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Key tension' })).toBeInTheDocument()
    expect(screen.getByText(MOCK_RESULT.synthesis.key_tension)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Synthesis' })).toBeInTheDocument()
    expect(screen.getByText(MOCK_RESULT.synthesis.reasoning)).toBeInTheDocument()
    expect(screen.getByText('Data as of 2026-10-02 · 2 sessions old')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /show reasoning|full debate|hide/i })).not.toBeInTheDocument()
  })

  it('has no disclosure control for Key tension or Synthesis', () => {
    show(populated())

    expect(screen.queryByRole('button', { name: /show|hide|expand|collapse/i })).not.toBeInTheDocument()
  })

  it('orders them: badge, Agreement, chips, Key tension, Synthesis, data line, Analysed time, Re-analyse', () => {
    show(populated({ report_saved: true, report_file: '2026-10-05_VCB.md' }))
    const order = [
      screen.getByText('Bullish lean'),
      screen.getByText(/^Agreement:/),
      screen.getByText('Technical Signal ↑ Bullish'),
      screen.getByRole('heading', { name: 'Key tension' }),
      screen.getByRole('heading', { name: 'Synthesis' }),
      screen.getByText(/^Data as of/),
      screen.getByText('Analysed 14:32'),
      screen.getByText(/report saved to/i),
      screen.getByRole('button', { name: 'Re-analyse VCB' }),
    ]

    for (let i = 1; i < order.length; i += 1) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING, `${i}`).toBeTruthy()
    }
  })

  it('labels the time the result was produced, and offers Re-analyse', () => {
    const state = { ...finished(populated()), analyse: vi.fn() }
    renderPanel(state)

    expect(screen.getByText('Analysed 14:32')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Re-analyse VCB' }))
    expect(state.analyse).toHaveBeenCalledTimes(1)
  })

  it('reads "current" at age 0 and "1 session old" at age 1', () => {
    const first = show(populated({ data_age_sessions: 0 }))
    expect(screen.getByText('Data as of 2026-10-02 · current')).toBeInTheDocument()
    first.unmount()

    show(populated({ data_age_sessions: 1 }))
    expect(screen.getByText('Data as of 2026-10-02 · 1 session old')).toBeInTheDocument()
  })

  it('a payload without data fields (an older server) still renders, with no data line', () => {
    show(MOCK_RESULT)

    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(screen.queryByText(/data as of/i)).not.toBeInTheDocument()
  })

  it('shows the language-model note once, above Key tension and Synthesis', () => {
    show(populated())

    const note = screen.getByText(LM_NOTE)
    expect(screen.getAllByText(LM_NOTE)).toHaveLength(1)
    expect(note.compareDocumentPosition(screen.getByRole('heading', { name: 'Key tension' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(note.compareDocumentPosition(screen.getByRole('heading', { name: 'Synthesis' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('renders Markdown bold as bold with no asterisks, and never as HTML, in Key tension and Synthesis', () => {
    const { container } = show(populated({
      synthesis: { ...MOCK_RESULT.synthesis, key_tension: 'The **key point** is the index.', reasoning: 'A **bold** summary. <b>not bold</b>' },
    }))

    expect(container.textContent).not.toContain('**')
    expect(screen.getByText('key point').tagName).toBe('STRONG')
    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.queryByText('not bold')).not.toBeInTheDocument()
    expect(container.querySelector('b')).toBeNull()
  })
})

describe('Verdict panel: Key tension', () => {
  it('says "Key tension unavailable" and shows no text as the key tension when it is null', () => {
    show(populated({ synthesis: { ...MOCK_RESULT.synthesis, key_tension: null } }))

    const block = screen.getByRole('heading', { name: 'Key tension' }).closest('section')
    expect(within(block).getByText('Key tension unavailable')).toBeInTheDocument()
    expect(within(block).queryByText(MOCK_RESULT.synthesis.key_tension)).not.toBeInTheDocument()
  })

  it('shows the key tension the model wrote under its heading', () => {
    show(populated())

    const block = screen.getByRole('heading', { name: 'Key tension' }).closest('section')
    expect(within(block).getByText(MOCK_RESULT.synthesis.key_tension)).toBeInTheDocument()
    expect(screen.queryByText(/key tension unavailable/i)).not.toBeInTheDocument()
  })
})

describe('Verdict panel: verdict badge and stance chips', () => {
  it.each(Object.entries(LABELS).filter(([verdict]) => verdict !== 'INSUFFICIENT_DATA'))('%s renders "%s"', (verdict, label) => {
    show(withVerdict(verdict))

    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it.each([
    ['STRONG_BUY_SIGNAL', '↑'],
    ['BUY_SIGNAL', '↑'],
    ['CAUTION_SIGNAL', '↓'],
    ['STRONG_CAUTION_SIGNAL', '↓'],
  ])('%s carries a hidden %s glyph beside its label, and the label is the text', (verdict, glyph) => {
    show(withVerdict(verdict))

    const badge = screen.getByText(LABELS[verdict])
    const mark = badge.querySelector('.verdict-badge__glyph')
    expect(mark).toHaveTextContent(glyph)
    expect(mark).toHaveAttribute('aria-hidden', 'true')
    expect(badge.childNodes[badge.childNodes.length - 1].textContent).toBe(LABELS[verdict])
  })

  it.each(['OBSERVE', 'SPLIT'])('%s has no arrow', (verdict) => {
    show(withVerdict(verdict))

    expect(screen.getByText(LABELS[verdict]).querySelector('.verdict-badge__glyph')).toBeNull()
  })

  it('INSUFFICIENT_DATA has no arrow and a dashed look of its own', () => {
    show(insufficient(['stale']))

    const badge = screen.getByText('Insufficient data')
    expect(badge.querySelector('.verdict-badge__glyph')).toBeNull()
    expect(badge).toHaveClass('verdict-badge--insufficient')
  })

  it('an unknown verdict renders "Unrecognised verdict", never the enum', () => {
    show(withVerdict('SOMETHING_NEW'))

    expect(screen.getByText('Unrecognised verdict')).toBeInTheDocument()
    expect(screen.queryByText(/SOMETHING_NEW/)).not.toBeInTheDocument()
  })

  it('every stance chip reads agent, arrow and word', () => {
    show(populated({
      round2: {
        technical: position('technical', 'bull', ['a']),
        news: position('news', 'neutral', ['b']),
        macro: position('macro', 'bear', ['c']),
      },
    }))

    expect(screen.getByText('Technical Signal ↑ Bullish')).toBeInTheDocument()
    expect(screen.getByText('News Context → Neutral')).toBeInTheDocument()
    expect(screen.getByText('Macro ↓ Bearish')).toBeInTheDocument()
  })

  it('tints bullish and bearish chips, and leaves neutral on the inset surface', () => {
    const { container } = show(populated({
      round2: {
        technical: position('technical', 'bull', ['a']),
        news: position('news', 'neutral', ['b']),
        macro: position('macro', 'bear', ['c']),
      },
    }))

    expect(container.querySelectorAll('.stance-chip--bull')).toHaveLength(1)
    expect(container.querySelectorAll('.stance-chip--neutral')).toHaveLength(1)
    expect(container.querySelectorAll('.stance-chip--bear')).toHaveLength(1)
  })
})

describe('Verdict panel: one agent unavailable', () => {
  it('marks it unavailable in the chips, counts the two live agents and names the one that did not answer', () => {
    show(oneDegraded())

    expect(screen.getByText('News Context unavailable')).toHaveClass('stance-chip--unavailable')
    expect(screen.getByText('Agreement: 2 of 2 live agents (News Context unavailable)')).toBeInTheDocument()
    expect(screen.queryByText(/unanimous/i)).not.toBeInTheDocument()
  })

  it('a split of two live agents reads "Split — 2 different positions (1 unavailable)"', () => {
    show(oneDegraded({
      verdict: 'SPLIT',
      agreement_level: 'split',
      round2: {
        technical: position('technical', 'bull', ['RSI above 55']),
        news: NEWS_DEGRADED,
        macro: position('macro', 'neutral', ['VN-Index flat']),
      },
    }))

    expect(screen.getByText('Agreement: Split — 2 different positions (1 unavailable)')).toBeInTheDocument()
    expect(screen.getByText('Split — no consensus')).toBeInTheDocument()
  })

  it('shows whatever verdict the server sends, never adding "Strong" itself', () => {
    show(oneDegraded({ verdict: 'OBSERVE' }))

    expect(screen.getByText('Observe')).toBeInTheDocument()
    expect(screen.queryByText(/strong/i)).not.toBeInTheDocument()
  })

  it('with no agent unavailable keeps the three-agent text and shows no unavailable mark', () => {
    show(populated())

    expect(screen.getByText('Agreement: Majority — 2 of 3 agents')).toBeInTheDocument()
    expect(screen.queryByText(/unavailable/i, { selector: '.stance-chip' })).not.toBeInTheDocument()
  })

  it('a split of three reads "Split — 3 different positions"', () => {
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

describe('Verdict panel: insufficient data', () => {
  it('after a run: states the reason with the age, offers Refresh and shows no verdict detail', () => {
    show(insufficient(['stale']))

    expect(screen.getByText('Insufficient data')).toBeInTheDocument()
    expect(screen.getByText('Data as of 2026-09-07 · 21 sessions old')).toBeInTheDocument()
    expect(screen.getByText('Stored prices are 21 sessions old. Refresh the ticker, then analyse again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh VCB' })).toBeInTheDocument()
    expect(screen.queryByText(/Technical Signal/)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Key tension' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Synthesis' })).not.toBeInTheDocument()
    expect(screen.queryByText(/agreement/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/report saved/i)).not.toBeInTheDocument()
  })

  it('before any run, from the ticker\'s own eligibility: the reason, Refresh, no Analyse, no request', () => {
    vi.mocked(useTickerContext).mockReturnValue(STALE_CONTEXT)
    const debate = vi.spyOn(tickersApi, 'runDebateAnalysis')

    renderPanel()

    expect(screen.getByText('Insufficient data')).toBeInTheDocument()
    expect(screen.getByText('Data as of 2026-09-07 · 21 sessions old')).toBeInTheDocument()
    expect(screen.getByText('Stored prices are 21 sessions old. Refresh the ticker, then analyse again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh VCB' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /analyse/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/stance|lean|bullish/i)).not.toBeInTheDocument()
    expect(debate).not.toHaveBeenCalled()
  })

  it('lists one sentence per reason, in the order given', () => {
    vi.mocked(useTickerContext).mockReturnValue(
      context({ eligible: false, reasons: ['delisted', 'stale', 'hard_quality_flag'], ageSessions: 21 }),
    )

    renderPanel()

    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'This ticker is delisted.',
      'Stored prices are 21 sessions old. Refresh the ticker, then analyse again.',
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

  it('with no reasons and two degraded agents, lists each agent and says fewer than two answered', () => {
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
    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
  })

  it('offers Re-analyse after an abstention on a ticker that is still eligible', () => {
    show(insufficient([], { eligibility: { eligible: true, reasons: [] }, agents_degraded: ['news', 'macro'] }))

    expect(screen.getByRole('button', { name: 'Re-analyse VCB' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh VCB' })).toBeInTheDocument()
  })

  it('offers no Re-analyse after a refusal on a ticker the catalog says is ineligible', () => {
    vi.mocked(useTickerContext).mockReturnValue(STALE_CONTEXT)

    show(insufficient(['stale']))

    expect(screen.queryByRole('button', { name: /analyse/i })).not.toBeInTheDocument()
  })

  it('says the age is unknown ("many") for a searched-in ticker with no age', () => {
    vi.mocked(useTickerContext).mockReturnValue(context({ asOf: '2026-09-07', ageSessions: null, reasons: ['stale'], eligible: false }))

    renderPanel()

    expect(screen.getByText('Data as of 2026-09-07')).toBeInTheDocument()
    expect(screen.getByText('Stored prices are many sessions old. Refresh the ticker, then analyse again.')).toBeInTheDocument()
  })

  it('shows the range block above it when asked to, since the band survives an ineligible ticker', async () => {
    vi.mocked(useTickerContext).mockReturnValue(context({ eligible: false, reasons: ['indicators_missing'] }))
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({
      ticker: 'VCB', as_of: '2026-10-06', status: 'ok', reasons: [], sigma_daily_pct: 1.4,
      range_5s_pct: 4.12, range_k: 1.1, range_coverage: 0.68, range_hit_rate: { rate: 0.68, n: 50 },
    })

    renderPanel(analysisState(), { showRange: true })

    expect(await screen.findByText('±4.12%')).toBeInTheDocument()
    expect(screen.getByText('Technical indicators are not available for the latest session.')).toBeInTheDocument()
  })
})

describe('Verdict panel: Refresh from the insufficient-data state', () => {
  const stale = () => vi.mocked(useTickerContext).mockReturnValue(STALE_CONTEXT)

  it('calls POST /tickers/{ticker}/load, like the Rail', async () => {
    stale()
    const load = vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VCB', status: 'ok', rows_loaded: 300 })
    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh VCB' }))

    await waitFor(() => expect(load).toHaveBeenCalledWith('VCB'))
  })

  it('is disabled while that ticker\'s load is in flight', async () => {
    stale()
    let finish
    vi.spyOn(tickersApi, 'loadTicker').mockReturnValue(new Promise((resolve) => (finish = resolve)))
    renderPanel()
    const button = screen.getByRole('button', { name: 'Refresh VCB' })

    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())

    finish({ ticker: 'VCB', status: 'ok', rows_loaded: 300 })
    await waitFor(() => expect(button).not.toBeDisabled())
  })

  it('invalidates the catalog, history and range of the ticker when it succeeds', async () => {
    stale()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VCB', status: 'ok', rows_loaded: 300 })
    const queryClient = newQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    renderWithQuery(<VerdictPanel ticker="VCB" analysis={analysisState()} showRange={false} />, queryClient)

    fireEvent.click(screen.getByRole('button', { name: 'Refresh VCB' }))

    await waitFor(() => expect(invalidate).toHaveBeenCalled())
    expect(invalidate.mock.calls.map(([filters]) => filters.queryKey)).toEqual([
      ['tickers'], ['ticker-history', 'VCB'], ['ticker-range', 'VCB'],
    ])
  })

  it.each([
    ['rate_limited', /try again in a moment/i],
    ['no_data', /unlikely to help/i],
  ])('says so in its own words when the load answers %s', async (status, message) => {
    stale()
    vi.spyOn(tickersApi, 'loadTicker').mockResolvedValue({ ticker: 'VCB', status })
    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh VCB' }))

    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('names a network failure and a server error differently', async () => {
    stale()
    const load = vi.spyOn(tickersApi, 'loadTicker')
    load.mockRejectedValueOnce(new ApiError('x', { status: 500, body: null }))
    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh VCB' }))
    expect(await screen.findByText('Something went wrong — try again')).toBeInTheDocument()

    load.mockRejectedValueOnce(new TypeError('fetch failed'))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh VCB' }))
    expect(await screen.findByText('Network error — try again')).toBeInTheDocument()
  })
})

describe('Verdict panel: failed', () => {
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

  const MESSAGES = [
    ['not loaded (404)', notLoaded, "VCB hasn't been loaded yet. Search for it in the top bar to load it first."],
    ['busy (429)', busy, 'Another analysis is already running; try again shortly.'],
    ["not configured (503), with the server's message", notConfigured, 'DEBATE_LLM_EFFORT is not valid. Supported: low, medium, high.'],
    ['server timeout (504)', serverTimeout, /timed out on the server/i],
    ['client time limit', clientTimeout, 'No answer after 200 s. The server may still be working; Analyse again to rejoin it.'],
    ["any other failure, with the server's detail", serverFailure, 'database is locked'],
    ['a network failure', unreachable, 'Network error — could not reach the server.'],
  ]

  it.each(MESSAGES)('%s says why, as an alert', (_name, make, message) => {
    renderPanel(analysisState({ error: make() }))

    expect(within(screen.getByRole('alert')).getByText(message)).toBeInTheDocument()
  })

  it('leads with a text marker, so the failure is named in words and not by colour', () => {
    renderPanel(analysisState({ error: busy() }))

    expect(within(screen.getByRole('alert')).getByText('Could not run the analysis:')).toBeInTheDocument()
  })

  it.each(MESSAGES)('%s keeps the disclaimer visible', (_name, make) => {
    renderPanel(analysisState({ error: make() }))

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeVisible()
    expect(screen.getByText('About this analysis').closest('details')).toHaveTextContent(FULL_DISCLAIMER)
  })

  it('any other failure also says the generic sentence, and a plain Error shows only that', () => {
    const first = renderPanel(analysisState({ error: serverFailure() }))
    expect(screen.getByText('Analysis failed — please try again.')).toBeInTheDocument()
    first.unmount()

    renderPanel(analysisState({ error: new Error('boom') }))
    expect(screen.getByText('Analysis failed — please try again.')).toBeInTheDocument()
    expect(screen.queryByText('boom')).not.toBeInTheDocument()
  })

  it('the client time limit is not described as an unreachable server', () => {
    renderPanel(analysisState({ error: clientTimeout() }))

    expect(screen.queryByText(/could not reach the server/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyse again' })).toBeInTheDocument()
  })

  it.each([
    ['busy (429)', busy, 'Retry'],
    ['not configured (503)', notConfigured, 'Retry'],
    ['server timeout (504)', serverTimeout, 'Retry'],
    ['client time limit', clientTimeout, 'Analyse again'],
    ['any other failure', serverFailure, 'Retry'],
    ['not loaded', notLoaded, 'Analyse again'],
  ])('%s offers "%s", which starts a run', (_name, make, label) => {
    const state = analysisState({ error: make(), analyse: vi.fn() })
    renderPanel(state)

    fireEvent.click(screen.getByRole('button', { name: label }))

    expect(state.analyse).toHaveBeenCalledTimes(1)
  })

  it('a structured detail (not a string) is ignored instead of crashing the panel', () => {
    const error = new ApiError('x', { status: 422, body: { detail: [{ loc: ['path'], msg: 'bad' }] } })

    renderPanel(analysisState({ error }))

    expect(screen.getByText('Analysis failed — please try again.')).toBeInTheDocument()
  })

  it('keeps the old result when a re-run fails, with the error shown above it', () => {
    const error = new ApiError('boom', { status: 500, body: { detail: 'boom' } })

    renderPanel(analysisState({ result: populated(), completedAt: DONE_AT, error }))

    const alert = screen.getByRole('alert')
    const verdict = screen.getByText('Bullish lean')
    expect(alert.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('Analysed 14:32')).toBeInTheDocument()
  })

  it('shows each ticker\'s kept result from its own state, with no new request, after switching away and back', () => {
    const states = { VCB: { ...finished(populated()), analyse: vi.fn() }, FPT: analysisState() }

    const vcb = renderPanel(states.VCB, { ticker: 'VCB' })
    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    vcb.unmount()

    const fpt = renderPanel(states.FPT, { ticker: 'FPT' })
    expect(screen.getByRole('button', { name: 'Analyse FPT' })).toBeInTheDocument()
    expect(screen.queryByText('Bullish lean')).not.toBeInTheDocument()
    fpt.unmount()

    renderPanel(states.VCB, { ticker: 'VCB' })
    expect(screen.getByText('Bullish lean')).toBeInTheDocument()
    expect(states.VCB.analyse).not.toHaveBeenCalled()
  })
})

describe('Verdict panel: the report line', () => {
  it('says where the report was saved, with the file name the server returned, when it was saved', () => {
    show(populated({ report_saved: true, report_file: '2026-10-05_VPB.md' }))

    expect(screen.getByText(/report saved to/i)).toHaveTextContent('Report saved to reports/2026-10-05_VPB.md')
  })

  it('does not guess the file name from the date and ticker', () => {
    show(populated({ report_saved: true, report_file: 'a-different-name.md', as_of: '2026-10-04' }))

    expect(screen.getByText(/report saved to/i)).toHaveTextContent('reports/a-different-name.md')
    expect(screen.queryByText(/2026-10-04_VCB/)).not.toBeInTheDocument()
  })

  it.each([
    ['false', { report_saved: false, report_file: null }],
    ['absent (an older server)', { report_saved: undefined, report_file: undefined }],
    ['true without a file name', { report_saved: true, report_file: null }],
  ])('claims nothing when report_saved is %s', (_name, fields) => {
    show(populated(fields))

    expect(screen.queryByText(/report saved/i)).not.toBeInTheDocument()
  })
})

describe('Verdict panel: disclaimer', () => {
  const STATES = {
    none: () => [analysisState(), { ticker: null }],
    ready: () => [analysisState(), {}],
    running: () => [running(), {}],
    failed: () => [analysisState({ error: new Error('boom') }), {}],
    result: () => [finished(populated()), {}],
    partial: () => [finished(oneDegraded()), {}],
    insufficient: () => [finished(insufficient(['stale'])), {}],
  }

  it.each(Object.keys(STATES))('%s: the inline text is visible, once, and the full text is inside "About this analysis"', (name) => {
    const [state, props] = STATES[name]()
    renderPanel(state, props)

    expect(screen.getAllByText(INLINE_DISCLAIMER)).toHaveLength(1)
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

  it('has no control that hides or collapses the inline text, and shows no repo path', () => {
    renderPanel()

    expect(screen.queryByRole('button', { name: /hide|dismiss|close/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByText(/DISCLAIMER\.md/)).not.toBeInTheDocument()
  })
})

describe('Verdict panel: fixed text (Rule 5 and Rule 6)', () => {
  function expectClean(container) {
    const text = container.textContent.replace(INLINE_DISCLAIMER, '').replace(FULL_DISCLAIMER, '')
    for (const guard of FORBIDDEN_TEXT) expect(text).not.toMatch(guard)
  }

  it.each([
    ['none', () => [analysisState(), { ticker: null }]],
    ['ready', () => [analysisState(), {}]],
    ['running', () => [running(), {}]],
    ['failed', () => [analysisState({ error: new Error('boom') }), {}]],
  ])('%s state uses no transaction verb, enum text, Confidence or Market Sentiment', (_name, make) => {
    const [state, props] = make()
    const { container } = renderPanel(state, props)

    expectClean(container)
  })

  it.each(Object.keys(LABELS))('%s uses none of them', (verdict) => {
    const data = verdict === 'INSUFFICIENT_DATA' ? insufficient(['stale']) : withVerdict(verdict)
    const { container } = show(data)

    expectClean(container)
  })

  it('an unavailable agent, and an ineligible ticker before any run, use none of them', () => {
    const first = show(oneDegraded())
    expectClean(first.container)
    first.unmount()

    vi.mocked(useTickerContext).mockReturnValue(STALE_CONTEXT)
    const second = renderPanel()
    expectClean(second.container)
  })

  it('never uses the Market Sentiment label', () => {
    const { container } = show(populated())

    expect(container.textContent).not.toMatch(/market sentiment/i)
  })
})

// The warn colours belong to Key tension alone, and a failure is named in the primary ink: both are
// stylesheet rules jsdom cannot compute, so they are read from the stylesheet's own text.
describe('Verdict panel stylesheet', () => {
  const css = readSrc('components/VerdictPanel/verdict-panel.css')

  it('uses the warn tokens only in rules about Key tension', () => {
    const offenders = parseRules(css)
      .filter((rule) => /--warn-/.test(rule.body) && !/tension/.test(rule.selector))
      .map((rule) => rule.selector)

    expect(offenders).toEqual([])
    expect(/--warn-/.test(css)).toBe(true)
  })

  it('draws a failure in the primary ink, with no up or down colour', () => {
    const [rule] = rulesFor(css, '.verdict-panel__failure')

    expect(declarations(rule.body).color).toBe('var(--ink)')
    expect(css).not.toMatch(/\.verdict-panel__failure[^{]*\{[^}]*--(up|down|candle)-/)
  })

  it('tints stance chips and badges with the up and down tokens, and the insufficient badge is dashed', () => {
    const bull = rulesFor(css, '.stance-chip--bull')[0]
    const bear = rulesFor(css, '.stance-chip--bear')[0]
    const insufficientRule = rulesFor(css, '.verdict-badge--insufficient')[0]

    expect(declarations(bull.body).color).toBe('var(--up-ink)')
    expect(declarations(bull.body).background).toBe('var(--up-bg)')
    expect(declarations(bear.body).color).toBe('var(--down-ink)')
    expect(declarations(bear.body).background).toBe('var(--down-bg)')
    expect(declarations(insufficientRule.body)['border-style']).toBe('dashed')
  })
})
