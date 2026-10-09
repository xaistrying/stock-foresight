// Debate results in the shape the backend serialises (backend/app/api/debate.py): `round1` only, no
// `round2` and no `synthesis`. Shared by the Verdict panel, Debate matrix and integration tests. Agent text avoids the words the Rule 6 guard
// forbids ("buy", "sell", "hold") so the guard can scan whole renderings.

export const position = (agentId, stance, reasoning, extra = {}) => ({
  agent_id: agentId,
  stance,
  reasoning,
  range_5s_pct: null,
  sigma_daily_pct: null,
  range_coverage: null,
  degraded_reason: null,
  ...extra,
})

export const MOCK_RESULT = {
  ticker: 'VCB',
  as_of: '2026-10-04',
  verdict: 'BUY_SIGNAL',
  agreement_level: 'majority',
  round1: {
    technical: position('technical', 'bull', ['RSI: 62.0', 'MACD histogram: 0.12']),
    news: position('news', 'bull', ['Positive Q3 earnings reported']),
    macro: position('macro', 'neutral', ['VN-Index trend: flat']),
  },
  range_5s_pct: 4.14,
  sigma_daily_pct: 1.85,
  range_coverage: 0.68,
  duration_ms: 4200,
}

/** A finished run with data fields, as the current server sends it. */
export function populated(overrides = {}) {
  return {
    ...MOCK_RESULT,
    data_as_of: '2026-10-02',
    data_age_sessions: 2,
    eligibility: { eligible: true, reasons: [] },
    agents_degraded: [],
    report_saved: false,
    report_file: null,
    ...overrides,
  }
}

export const NEWS_DEGRADED = position('news', 'neutral', ['PLACEHOLDER news'], { degraded_reason: 'llm_failed' })

/** A refusal (reasons) or an abstention (no reasons, degraded agents), verdict INSUFFICIENT_DATA. */
export function insufficient(reasons, overrides = {}) {
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
    range_5s_pct: null,
    sigma_daily_pct: null,
    range_coverage: null,
    duration_ms: 0,
    ...overrides,
  }
}

export function withVerdict(verdict, extra = {}) {
  return populated({ verdict, ...extra })
}

/** One agent unavailable: News, with the two live agents on the same stance. */
export function oneDegraded(overrides = {}) {
  return populated({
    round1: {
      technical: position('technical', 'bull', ['RSI: 62.0']),
      news: NEWS_DEGRADED,
      macro: position('macro', 'bull', ['VN-Index trend: up (+)']),
    },
    agents_degraded: ['news'],
    ...overrides,
  })
}

/** What useDebateAnalysis returns. */
export function analysisState(overrides = {}) {
  return {
    analyse: () => {},
    isPending: false,
    startedAt: null,
    result: null,
    completedAt: null,
    error: null,
    ...overrides,
  }
}

export const DONE_AT = new Date(2026, 9, 7, 14, 32).getTime() // local time: "Analysed 14:32"

export const LABELS = {
  STRONG_BUY_SIGNAL: 'Strong bullish lean',
  BUY_SIGNAL: 'Bullish lean',
  OBSERVE: 'Observe',
  CAUTION_SIGNAL: 'Bearish lean',
  STRONG_CAUTION_SIGNAL: 'Strong bearish lean',
  SPLIT: 'Split — no consensus',
  INSUFFICIENT_DATA: 'Insufficient data',
}

// The guard of design Decision 11: fixed dashboard text has no transaction verbs, enum text,
// Confidence or Market Sentiment.
export const FORBIDDEN_TEXT = [
  /\b(buy|sell|hold)\b/i,
  /[A-Z]+_SIGNAL\b|INSUFFICIENT_DATA/,
  /\bconfiden(ce|t)\b/i,
  /market sentiment/i,
]
