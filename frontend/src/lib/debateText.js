import { ApiError } from '../api/client'
import { DEBATE_CLIENT_TIMEOUT_MS } from '../api/tickers'

// Pure text and display rules for the Verdict panel and the Debate matrix, moved out of the earlier
// single debate component unchanged in behaviour, except where the new layout changed what they say.

/** The sentence "Analysis takes about N seconds." uses this, from one place (design Open Question 9). */
export const TYPICAL_ANALYSIS_SECONDS = 45

// Verdict display config. Labels are non-transactional (Rule 6); the keys are the API enum. `arrow` is
// shown only for a directional lean, `tone` picks the badge's look.
export const VERDICT_CONFIG = {
  STRONG_BUY_SIGNAL: { label: 'Strong bullish lean', arrow: '↑', tone: 'bull' },
  BUY_SIGNAL: { label: 'Bullish lean', arrow: '↑', tone: 'bull' },
  OBSERVE: { label: 'Observe', arrow: null, tone: 'neutral' },
  CAUTION_SIGNAL: { label: 'Bearish lean', arrow: '↓', tone: 'bear' },
  STRONG_CAUTION_SIGNAL: { label: 'Strong bearish lean', arrow: '↓', tone: 'bear' },
  SPLIT: { label: 'Split — no consensus', arrow: null, tone: 'neutral' },
  INSUFFICIENT_DATA: { label: 'Insufficient data', arrow: null, tone: 'insufficient' },
}
export const UNKNOWN_VERDICT = { label: 'Unrecognised verdict', arrow: null, tone: 'neutral' }

export const AGENT_ORDER = ['technical', 'news', 'macro']

// Agent labels — Rule 5: TechnicalAgent = "Technical Signal", NewsAgent = "News Context".
const AGENT_LABELS = { technical: 'Technical Signal', news: 'News Context', macro: 'Macro' }
export const agentLabel = (agentId) => AGENT_LABELS[agentId] ?? agentId

const STANCE_GLYPHS = { bull: '↑', neutral: '→', bear: '↓' }
const STANCE_WORDS = { bull: 'Bullish', neutral: 'Neutral', bear: 'Bearish' }
/** "↑ Bullish": the arrow always travels with the word (colour alone never says direction). */
export const stanceMark = (stance) => `${STANCE_GLYPHS[stance] ?? '→'} ${STANCE_WORDS[stance] ?? stance}`

// Why an agent has no vote (backend `degraded_reason`).
export const DEGRADED_REASON_TEXT = {
  agent_error: 'The agent failed to run.',
  no_input: 'No usable input data.',
  llm_failed: 'The language-model analysis failed.',
  round2_failed: 'Round 2 failed; its Round 1 position is shown but not counted.',
}
export const degradedText = (position) => DEGRADED_REASON_TEXT[position.degraded_reason] ?? position.degraded_reason

// The stage the server reports while a run is going (progress `stage`). Not verdict labels.
export const STAGE_LABELS = {
  round1: 'Running agents…',
  round2: 'Comparing positions…',
  synthesis: 'Synthesising…',
}

const GENERIC_FAILURE = 'Analysis failed — please try again.'

/**
 * What to tell the user about a failed run, from the backend's status and machine-readable `code`.
 * `retry` is the label of the button that runs it again, or null.
 */
export function describeFailure(error, ticker) {
  if (!(error instanceof ApiError)) return { message: GENERIC_FAILURE, retry: 'Retry' }

  if (error.timedOut) {
    // The client gave up; the server may still be working, and asking again joins its run.
    return {
      message: `No answer after ${DEBATE_CLIENT_TIMEOUT_MS / 1000} s. The server may still be working; Analyse again to rejoin it.`,
      retry: 'Analyse again',
    }
  }
  const code = error.body?.code
  if (error.status === 404) {
    // The error outlives a remount (it lives in the mutation cache), so there must be a way to run
    // again once the ticker has been loaded.
    return {
      message: `${ticker} hasn't been loaded yet. Search for it in the top bar to load it first.`,
      retry: 'Analyse again',
    }
  }
  if (error.status === 429 && code === 'debate_busy') {
    return { message: 'Another analysis is already running; try again shortly.', retry: 'Retry' }
  }
  if (error.status === 503 && code === 'debate_not_configured') {
    return { message: error.message, retry: 'Retry' } // the server names the setting to fix
  }
  if (error.status === 504 && code === 'debate_timeout') {
    return { message: 'The analysis timed out on the server. Try again shortly.', retry: 'Retry' }
  }
  // Anything else: the generic sentence plus whatever the server said (or, with no response at all,
  // the client's own network-error text).
  const raw = error.body?.detail ?? (error.status == null ? error.message : null)
  // Only a string is rendered: a structured `detail` (a 422 body, another server) would crash React.
  return { message: GENERIC_FAILURE, detail: typeof raw === 'string' ? raw : null, retry: 'Retry' }
}

/** Why a ticker was refused (backend `eligibility.reasons`), one plain sentence per reason. */
export function reasonSentence(reason, ageSessions) {
  switch (reason) {
    case 'delisted':
      return 'This ticker is delisted.'
    case 'insufficient_history':
      return 'Not enough price history (at least 65 sessions are needed).'
    case 'stale':
      return `Stored prices are ${ageSessions ?? 'many'} sessions old. Refresh the ticker, then analyse again.`
    case 'near_gap':
      return 'The price history has missing sessions.'
    case 'hard_quality_flag':
      return 'A recent price failed a data-quality check.'
    case 'indicators_missing':
      return 'Technical indicators are not available for the latest session.'
    default:
      return reason
  }
}

/**
 * The vote count, labelled Agreement and never Confidence (Rule 4). It counts live agents only: a
 * degraded agent's placeholder stance is not a vote. With an agent unavailable it names the one(s)
 * that did not answer; a split keeps the count of unavailable ones.
 */
export function agreementText(result) {
  const { agreement_level: level, round2 } = result
  const positions = Object.entries(round2)
  const live = positions.filter(([, position]) => !position.degraded_reason)
  const unavailable = positions.filter(([, position]) => position.degraded_reason).map(([id]) => agentLabel(id))

  if (level === 'split') {
    const suffix = unavailable.length > 0 ? ` (${unavailable.length} unavailable)` : ''
    return `Agreement: Split — ${live.length} different positions${suffix}`
  }
  const counts = live.reduce((acc, [, position]) => ({ ...acc, [position.stance]: (acc[position.stance] || 0) + 1 }), {})
  const top = Math.max(0, ...Object.values(counts))
  if (unavailable.length > 0) {
    return `Agreement: ${top} of ${live.length} live agents (${unavailable.join(', ')} unavailable)`
  }
  return `Agreement: ${level.charAt(0).toUpperCase() + level.slice(1)} — ${top} of ${live.length} agents`
}

/** "Data as of 2026-10-02 · 2 sessions old", "· current" at age 0, the date alone when the age is absent. */
export function dataDateText({ data_as_of: date, data_age_sessions: age }) {
  if (age == null) return `Data as of ${date}`
  const ageText = age === 0 ? 'current' : `${age} session${age === 1 ? '' : 's'} old`
  return `Data as of ${date} · ${ageText}`
}

/** Local "HH:MM" of a client-clock timestamp. */
export function formatClock(ms) {
  const time = new Date(ms)
  return `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`
}
