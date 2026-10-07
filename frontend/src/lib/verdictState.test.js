import { describe, expect, it } from 'vitest'
import { chooseVerdictState, resolveEligibility } from './verdictState'
import { insufficient, oneDegraded, populated } from '../test/debateFixtures'

const ELIGIBLE = { eligible: true, reasons: [], age_sessions: 0 }
const STALE = { eligible: false, reasons: ['stale'], age_sessions: 21 }
const idle = { isPending: false, error: null }

const choose = (overrides = {}) =>
  chooseVerdictState({ ticker: 'VCB', run: idle, result: null, eligibility: ELIGIBLE, range: null, ...overrides })

describe('chooseVerdictState', () => {
  it('is "none" with no ticker, whatever else is known', () => {
    expect(choose({ ticker: null, result: populated(), run: { isPending: true } })).toBe('none')
  })

  it('is "ready" for an eligible ticker with no run and no result', () => {
    expect(choose()).toBe('ready')
  })

  it('is "ready" while eligibility is not known yet', () => {
    expect(choose({ eligibility: null, range: null })).toBe('ready')
  })

  it('is "insufficient" for an ineligible ticker with no run, with no request needed', () => {
    expect(choose({ eligibility: STALE })).toBe('insufficient')
  })

  it('a pending run is "running", over a kept result, an error and ineligibility', () => {
    expect(choose({ run: { isPending: true, error: new Error('x') }, result: populated(), eligibility: STALE })).toBe('running')
  })

  it('a failed run is "failed", with or without a kept result beneath it', () => {
    expect(choose({ run: { isPending: false, error: new Error('x') } })).toBe('failed')
    expect(choose({ run: { isPending: false, error: new Error('x') }, result: populated() })).toBe('failed')
  })

  it('a finished run is "result", or "partial" when an agent did not vote', () => {
    expect(choose({ result: populated() })).toBe('result')
    expect(choose({ result: oneDegraded() })).toBe('partial')
  })

  it('a result whose verdict is INSUFFICIENT_DATA is "insufficient"', () => {
    expect(choose({ result: insufficient(['stale']) })).toBe('insufficient')
    expect(choose({ result: insufficient([], { agents_degraded: ['news', 'macro'] }) })).toBe('insufficient')
  })

  it('a kept result still shows for a ticker that has since become ineligible', () => {
    expect(choose({ result: populated(), eligibility: STALE })).toBe('result')
  })

  it('falls back to /range for a ticker with no catalog entry', () => {
    const refused = { status: 'ineligible', reasons: ['stale'], range_5s_pct: null }
    const served = { status: 'ok', reasons: [], range_5s_pct: 4.12 }

    expect(choose({ eligibility: null, range: refused })).toBe('insufficient')
    expect(choose({ eligibility: null, range: served })).toBe('ready')
  })

  it('prefers the catalog\'s eligibility over /range when both exist', () => {
    const served = { status: 'ok', reasons: [], range_5s_pct: 4.12 }

    expect(choose({ eligibility: STALE, range: served })).toBe('insufficient')
  })
})

describe('resolveEligibility', () => {
  it('reads the catalog summary as it is', () => {
    expect(resolveEligibility(STALE, null)).toEqual({ eligible: false, reasons: ['stale'], ageSessions: 21 })
  })

  it('takes reasons and status from /range when there is no summary, and no age', () => {
    expect(resolveEligibility(null, { status: 'ineligible', reasons: ['stale'] })).toEqual({
      eligible: false,
      reasons: ['stale'],
      ageSessions: null,
    })
    expect(resolveEligibility(undefined, { status: 'ok', reasons: [] })).toEqual({
      eligible: true,
      reasons: [],
      ageSessions: null,
    })
  })

  it('does not know when neither answers', () => {
    expect(resolveEligibility(null, null)).toEqual({ eligible: null, reasons: [], ageSessions: null })
  })
})
