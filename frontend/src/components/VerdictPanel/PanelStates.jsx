import { useEffect, useState } from 'react'
import { describeLoadOutcome, useIsTickerLoading, useLoadTicker } from '../../hooks/useLoadTicker'
import {
  STAGE_LABELS,
  TYPICAL_ANALYSIS_SECONDS,
  agentLabel,
  dataDateText,
  degradedText,
  describeFailure,
  reasonSentence,
} from '../../lib/debateText'
import { VerdictBadge } from './VerdictParts'

/** Ready: the ticker can be analysed and no run exists. Says how long it takes before it starts. */
export function ReadyBody({ ticker, onAnalyse }) {
  return (
    <div className="verdict-panel__ready">
      <button type="button" className="verdict-panel__button" onClick={onAnalyse}>
        Analyse {ticker}
      </button>
      <p className="verdict-panel__meta t-small">Analysis takes about {TYPICAL_ANALYSIS_SECONDS} seconds.</p>
    </div>
  )
}

// Whole seconds since `startedAt`, re-read every second. Mount it only while a run is going
// (RunningState does), so every run starts a fresh timer.
function useElapsedSeconds(startedAt) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return Math.max(0, Math.floor((now - startedAt) / 1000))
}

/**
 * Running: the stage label comes from the server (the progress poll), never from a timer; the elapsed
 * time is counted here. Until the first poll answers, the first stage's label stands in. Never a
 * spinner alone.
 */
export function RunningState({ stage, startedAt }) {
  const elapsed = useElapsedSeconds(startedAt)
  return (
    <div className="verdict-panel__running">
      <span className="verdict-panel__spinner" aria-hidden="true" />
      <p className="verdict-panel__stage t-body" role="status">
        {STAGE_LABELS[stage] ?? STAGE_LABELS.round1}
      </p>
      <span className="verdict-panel__elapsed t-num">{elapsed} s</span>
      <p className="verdict-panel__meta t-small">You can switch ticker; the result is kept.</p>
    </div>
  )
}

/**
 * Failed: the reason in plain words, in the primary ink (the design has no error colour, and red would
 * read as a bearish cue), led by a text marker, and a retry. A kept result stays visible beneath it.
 */
export function FailureNotice({ error, ticker, onRetry }) {
  const { message, detail, retry } = describeFailure(error, ticker)
  return (
    <div className="verdict-panel__failure-box" role="alert">
      <p className="verdict-panel__failure t-body">
        <span className="verdict-panel__failure-marker t-label">Could not run the analysis:</span> <span>{message}</span>
      </p>
      {detail ? <p className="verdict-panel__meta t-small">{detail}</p> : null}
      {retry ? (
        <button type="button" className="verdict-panel__button" onClick={onRetry}>
          {retry}
        </button>
      ) : null}
    </div>
  )
}

// Refresh runs the same load a Rail row's Refresh does (same mutation key, so it is disabled while any
// load of this ticker is in flight, and a completed one refreshes the catalog, history and range).
function RefreshAction({ ticker }) {
  const loadMutation = useLoadTicker(ticker)
  const isLoading = useIsTickerLoading(ticker)
  const message = describeLoadOutcome(loadMutation, ticker)
  return (
    <>
      <button
        type="button"
        className="verdict-panel__button verdict-panel__button--secondary"
        disabled={isLoading}
        onClick={() => loadMutation.mutate()}
      >
        Refresh {ticker}
      </button>
      {message ? (
        <p className="verdict-panel__meta t-small" role="alert">
          {message}
        </p>
      ) : null}
    </>
  )
}

// Why the panel is in this state, as one sentence per reason, in the order given. From a run that
// refused (its eligibility), a run that abstained after the agents ran (each degraded agent and why), or
// the ticker's own eligibility before any run.
function Reasons({ result, context }) {
  if (result && (result.eligibility?.reasons ?? []).length === 0) {
    const degraded = result.agents_degraded ?? []
    return (
      <>
        <p className="verdict-panel__meta t-small">Fewer than two agents produced a usable position.</p>
        <ul className="verdict-panel__reasons t-body">
          {degraded.map((id) => (
            <li key={id}>{`${agentLabel(id)} — ${degradedText(result.round2[id] ?? {})}`}</li>
          ))}
        </ul>
      </>
    )
  }
  const reasons = result ? result.eligibility.reasons : context.reasons
  const age = result ? result.data_age_sessions : context.ageSessions
  return (
    <ul className="verdict-panel__reasons t-body">
      {reasons.map((reason) => (
        <li key={reason}>{reasonSentence(reason, age)}</li>
      ))}
    </ul>
  )
}

/**
 * Insufficient data: the ticker cannot be analysed (known from its eligibility, before any run) or a
 * run refused or abstained. Reasons in plain words, the data date and age when known, and Refresh.
 * No verdict, Agreement, stance, Key tension or Synthesis, and no report-saved note.
 */
export function InsufficientBody({ ticker, result, context, canReanalyse, onAnalyse }) {
  const dataLine = result
    ? result.data_as_of && dataDateText(result)
    : context.asOf && dataDateText({ data_as_of: context.asOf, data_age_sessions: context.ageSessions })
  return (
    <div className="verdict-panel__insufficient">
      <VerdictBadge verdict="INSUFFICIENT_DATA" />
      {dataLine ? <p className="verdict-panel__meta t-small">{dataLine}</p> : null}
      <Reasons result={result} context={context} />
      <RefreshAction ticker={ticker} />
      {canReanalyse ? (
        <button type="button" className="verdict-panel__button verdict-panel__button--secondary" onClick={onAnalyse}>
          Re-analyse {ticker}
        </button>
      ) : null}
    </div>
  )
}
