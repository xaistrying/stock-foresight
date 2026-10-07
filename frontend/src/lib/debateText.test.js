import { describe, expect, it } from 'vitest'
import {
  TYPICAL_ANALYSIS_SECONDS,
  agentLabel,
  agreementText,
  dataDateText,
  degradedText,
  describeFailure,
  formatClock,
  reasonSentence,
  VERDICT_CONFIG,
} from './debateText'
import { ApiError } from '../api/client'
import { MOCK_RESULT, NEWS_DEGRADED, oneDegraded, populated, position } from '../test/debateFixtures'

describe('verdict labels', () => {
  it('maps the seven API values to display labels, with an arrow only on a directional lean', () => {
    expect(Object.fromEntries(Object.entries(VERDICT_CONFIG).map(([k, v]) => [k, [v.label, v.arrow]]))).toEqual({
      STRONG_BUY_SIGNAL: ['Strong bullish lean', '↑'],
      BUY_SIGNAL: ['Bullish lean', '↑'],
      OBSERVE: ['Observe', null],
      CAUTION_SIGNAL: ['Bearish lean', '↓'],
      STRONG_CAUTION_SIGNAL: ['Strong bearish lean', '↓'],
      SPLIT: ['Split — no consensus', null],
      INSUFFICIENT_DATA: ['Insufficient data', null],
    })
  })
})

describe('agentLabel', () => {
  it('names agents by what they read (Rule 5) and passes an unknown id through', () => {
    expect([agentLabel('technical'), agentLabel('news'), agentLabel('macro')]).toEqual([
      'Technical Signal',
      'News Context',
      'Macro',
    ])
    expect(agentLabel('other')).toBe('other')
  })
})

describe('agreementText', () => {
  it('with no unavailable agent, unanimous reads "Agreement: Unanimous — 3 of 3 agents"', () => {
    const result = populated({
      agreement_level: 'unanimous',
      round2: {
        technical: position('technical', 'bull', ['a']),
        news: position('news', 'bull', ['b']),
        macro: position('macro', 'bull', ['c']),
      },
    })

    expect(agreementText(result)).toBe('Agreement: Unanimous — 3 of 3 agents')
  })

  it('with no unavailable agent, a majority reads "Agreement: Majority — 2 of 3 agents"', () => {
    expect(agreementText(populated())).toBe('Agreement: Majority — 2 of 3 agents')
  })

  it('a three-way split reads "Split — 3 different positions"', () => {
    const result = populated({
      agreement_level: 'split',
      round2: {
        technical: position('technical', 'bull', ['a']),
        news: position('news', 'neutral', ['b']),
        macro: position('macro', 'bear', ['c']),
      },
    })

    expect(agreementText(result)).toBe('Agreement: Split — 3 different positions')
  })

  it('counts live agents only and names the one that did not answer', () => {
    expect(agreementText(oneDegraded())).toBe('Agreement: 2 of 2 live agents (News Context unavailable)')
  })

  it('a split of two live agents keeps the count of unavailable ones', () => {
    const result = oneDegraded({
      agreement_level: 'split',
      round2: {
        technical: position('technical', 'bull', ['a']),
        news: NEWS_DEGRADED,
        macro: position('macro', 'neutral', ['b']),
      },
    })

    expect(agreementText(result)).toBe('Agreement: Split — 2 different positions (1 unavailable)')
  })

  it('never says "unanimous" while any agent is unavailable', () => {
    expect(agreementText(oneDegraded({ agreement_level: 'unanimous' }))).not.toMatch(/unanimous/i)
  })

  it('names every unavailable agent', () => {
    const macro = position('macro', 'neutral', ['x'], { degraded_reason: 'agent_error' })
    const result = oneDegraded({ round2: { ...oneDegraded().round2, macro } })

    expect(agreementText(result)).toBe('Agreement: 1 of 1 live agents (News Context, Macro unavailable)')
  })
})

describe('dataDateText', () => {
  it.each([
    [2, 'Data as of 2026-10-02 · 2 sessions old'],
    [1, 'Data as of 2026-10-02 · 1 session old'],
    [0, 'Data as of 2026-10-02 · current'],
    [null, 'Data as of 2026-10-02'],
    [undefined, 'Data as of 2026-10-02'],
  ])('age %s reads "%s"', (age, text) => {
    expect(dataDateText({ data_as_of: '2026-10-02', data_age_sessions: age })).toBe(text)
  })
})

describe('reasonSentence', () => {
  it.each([
    ['delisted', 'This ticker is delisted.'],
    ['insufficient_history', 'Not enough price history (at least 65 sessions are needed).'],
    ['near_gap', 'The price history has missing sessions.'],
    ['hard_quality_flag', 'A recent price failed a data-quality check.'],
    ['indicators_missing', 'Technical indicators are not available for the latest session.'],
  ])('%s has its own sentence', (reason, sentence) => {
    expect(reasonSentence(reason, 3)).toBe(sentence)
  })

  it('stale names the age, and says "many" when it is not known', () => {
    expect(reasonSentence('stale', 21)).toBe('Stored prices are 21 sessions old. Refresh the ticker, then analyse again.')
    expect(reasonSentence('stale', null)).toBe('Stored prices are many sessions old. Refresh the ticker, then analyse again.')
  })

  it('passes an unknown reason through', () => {
    expect(reasonSentence('something_new', 1)).toBe('something_new')
  })
})

describe('degradedText', () => {
  it('gives the plain-language reason for each backend code', () => {
    expect(degradedText({ degraded_reason: 'agent_error' })).toBe('The agent failed to run.')
    expect(degradedText({ degraded_reason: 'no_input' })).toBe('No usable input data.')
    expect(degradedText({ degraded_reason: 'llm_failed' })).toBe('The language-model analysis failed.')
    expect(degradedText({ degraded_reason: 'round2_failed' })).toBe(
      'Round 2 failed; its Round 1 position is shown but not counted.',
    )
  })
})

describe('describeFailure', () => {
  it('says a ticker that was never loaded has to be loaded first, and offers to run again', () => {
    const error = new ApiError('x', { status: 404, body: {} })

    expect(describeFailure(error, 'VCB')).toEqual({
      message: "VCB hasn't been loaded yet. Search for it in the top bar to load it first.",
      retry: 'Analyse again',
    })
  })

  it('keeps the busy, timeout and generic messages and labels', () => {
    expect(describeFailure(new ApiError('x', { status: 429, body: { code: 'debate_busy' } }), 'V')).toMatchObject({
      message: 'Another analysis is already running; try again shortly.',
      retry: 'Retry',
    })
    expect(describeFailure(new ApiError('x', { status: 504, body: { code: 'debate_timeout' } }), 'V')).toMatchObject({
      message: 'The analysis timed out on the server. Try again shortly.',
    })
    expect(describeFailure(new Error('boom'), 'V')).toEqual({ message: 'Analysis failed — please try again.', retry: 'Retry' })
  })

  it('ignores a detail that is not a string', () => {
    const error = new ApiError('x', { status: 422, body: { detail: [{ msg: 'bad' }] } })

    expect(describeFailure(error, 'V').detail).toBeNull()
  })
})

describe('constants and clock', () => {
  it('has one duration for the "about 45 seconds" notice', () => {
    expect(TYPICAL_ANALYSIS_SECONDS).toBe(45)
  })

  it('formats a client timestamp as local HH:MM', () => {
    expect(formatClock(new Date(2026, 9, 7, 9, 5).getTime())).toBe('09:05')
  })

  it('the shared result fixture is a bullish majority', () => {
    expect(MOCK_RESULT.verdict).toBe('BUY_SIGNAL')
  })
})
