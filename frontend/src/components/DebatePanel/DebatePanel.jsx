import { useEffect, useState } from 'react'
import { useDebateAnalysis } from '../../hooks/useDebateAnalysis'
import { useDebateProgress } from '../../hooks/useDebateProgress'
import { ApiError } from '../../api/client'
import { DEBATE_CLIENT_TIMEOUT_MS } from '../../api/tickers'
import { FULL_DISCLAIMER, INLINE_DISCLAIMER, LM_NOTE } from '../../lib/disclaimer'
import './debate-panel.css'

// ------------------------------------------------------------------ #
// Constants
// ------------------------------------------------------------------ #

// Verdict display config. Labels are non-transactional (Rule 6); the keys are the API enum.
const VERDICT_CONFIG = {
  STRONG_BUY_SIGNAL:      { label: 'Strong bullish lean',     className: 'debate-panel__verdict--strong-bull' },
  BUY_SIGNAL:             { label: 'Bullish lean',            className: 'debate-panel__verdict--bull' },
  OBSERVE:                { label: 'Observe',                 className: 'debate-panel__verdict--neutral' },
  CAUTION_SIGNAL:         { label: 'Bearish lean',            className: 'debate-panel__verdict--bear' },
  STRONG_CAUTION_SIGNAL:  { label: 'Strong bearish lean',     className: 'debate-panel__verdict--strong-bear' },
  SPLIT:                  { label: 'Split — no consensus',    className: 'debate-panel__verdict--split' },
  INSUFFICIENT_DATA:      { label: 'Insufficient data',       className: 'debate-panel__verdict--insufficient' },
}

const STANCE_ICONS = { bull: '↑', neutral: '→', bear: '↓' }
const STANCE_LABELS = { bull: 'Bullish', neutral: 'Neutral', bear: 'Bearish' }

// Agent labels — Rule 5: TechnicalAgent = "Technical Signal", NewsAgent = "News Context"
const AGENT_LABELS = {
  technical: 'Technical Signal',
  news: 'News Context',
  macro: 'Macro',
}

// Why an agent has no vote (backend `degraded_reason`).
const DEGRADED_REASON_TEXT = {
  agent_error: 'The agent failed to run.',
  no_input: 'No usable input data.',
  llm_failed: 'The language-model analysis failed.',
  round2_failed: 'Round 2 failed; its Round 1 position is shown but not counted.',
}

// The stage the server reports while a run is going (progress `stage`). Not verdict labels.
const STAGE_LABELS = {
  round1: 'Running agents…',
  round2: 'Comparing positions…',
  synthesis: 'Synthesising…',
}

const GENERIC_FAILURE = 'Analysis failed — please try again.'

// What to tell the user about a failed run, from the backend's status and machine-readable
// `code` (design Decision 11). `retry` is the label of the button that runs it again, or null.
function describeFailure(error, ticker) {
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
    return { message: `${ticker} hasn't been loaded yet. Load it from the ticker panel first.`, retry: 'Analyse again' }
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
  // Anything else: the generic sentence plus whatever the server said (or, with no response at
  // all, the client's own network-error text).
  const raw = error.body?.detail ?? (error.status == null ? error.message : null)
  // Only a string is rendered: a structured `detail` (a 422 body, another server) would crash React.
  return { message: GENERIC_FAILURE, detail: typeof raw === 'string' ? raw : null, retry: 'Retry' }
}

// Why a ticker was refused (backend `eligibility.reasons`), in the backend's order.
function reasonSentence(reason, ageSessions) {
  switch (reason) {
    case 'delisted': return 'This ticker is delisted.'
    case 'insufficient_history': return 'Not enough price history (at least 65 sessions are needed).'
    case 'stale':
      return `Stored prices are ${ageSessions ?? 'many'} sessions old. Refresh the ticker in the ticker panel, then analyse again.`
    case 'near_gap': return 'The price history has missing sessions.'
    case 'hard_quality_flag': return 'A recent price failed a data-quality check.'
    case 'indicators_missing': return 'Technical indicators are not available for the latest session.'
    default: return reason
  }
}

// ------------------------------------------------------------------ #
// Helpers
// ------------------------------------------------------------------ #

function agentLabel(agentId) {
  return AGENT_LABELS[agentId] ?? agentId
}

function stanceIcon(stance) {
  return STANCE_ICONS[stance] ?? '→'
}

function degradedText(position) {
  return DEGRADED_REASON_TEXT[position.degraded_reason] ?? position.degraded_reason
}

// Counts live agents only: a degraded agent's placeholder stance is not a vote.
function agreementText(result) {
  const { agreement_level, round2 } = result
  const positions = Object.values(round2)
  const live = positions.filter(p => !p.degraded_reason)
  const unavailable = positions.length - live.length
  const suffix = unavailable > 0 ? ` (${unavailable} unavailable)` : ''
  if (agreement_level === 'split') return `Agreement: Split — ${live.length} different positions${suffix}`

  const counts = live.reduce((acc, p) => { acc[p.stance] = (acc[p.stance] || 0) + 1; return acc }, {})
  const n = Math.max(0, ...Object.values(counts))
  if (unavailable > 0) return `Agreement: ${n} of ${live.length} live agents${suffix}`
  return `Agreement: ${agreement_level.charAt(0).toUpperCase() + agreement_level.slice(1)} — ${n} of ${live.length} agents`
}

// Model text often carries Markdown bold (**like this**). Shown as bold, never as raw asterisks, and
// without HTML: the text is split and rebuilt as React nodes, so nothing in it is interpreted.
const BOLD = /\*\*([^*]+)\*\*/g

function Inline({ text }) {
  const parts = text.split(BOLD) // odd indexes are the bold spans
  return parts.map((part, i) => (i % 2 === 1 ? <strong key={i}>{part}</strong> : part))
}

// Local "HH:MM" of a client-clock timestamp.
function formatClock(ms) {
  const time = new Date(ms)
  return `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`
}

function dataDateText(result) {
  const age = result.data_age_sessions
  const ageText = age === 0 ? 'current' : `${age} session${age === 1 ? '' : 's'} old`
  return age == null ? `Data as of ${result.data_as_of}` : `Data as of ${result.data_as_of} · ${ageText}`
}

// ------------------------------------------------------------------ #
// Sub-components
// ------------------------------------------------------------------ #

function StanceRow({ round2 }) {
  return (
    <div className="debate-panel__stance-row">
      {Object.entries(round2).map(([id, pos]) => (
        pos.degraded_reason ? (
          <span key={id} className="debate-panel__stance-chip debate-panel__stance-chip--degraded">
            {agentLabel(id)} ⚠ unavailable
          </span>
        ) : (
          <span key={id} className={`debate-panel__stance-chip debate-panel__stance-chip--${pos.stance}`}>
            {agentLabel(id)} {stanceIcon(pos.stance)}
          </span>
        )
      ))}
    </div>
  )
}

function AgentCard({ agentId, position }) {
  const label = agentLabel(agentId)
  const icon = stanceIcon(position.stance)
  const stanceLabel = STANCE_LABELS[position.stance] ?? position.stance

  if (position.degraded_reason) {
    return (
      <div className="debate-panel__agent-card debate-panel__agent-card--degraded">
        <h4 className="debate-panel__agent-label">
          {label} <span className="debate-panel__stance-icon">⚠ Unavailable</span>
        </h4>
        <p className="debate-panel__degraded-note">{degradedText(position)}</p>
        <ul className="debate-panel__reasoning-list">
          {position.reasoning.map((bullet, i) => (
            <li key={i}><Inline text={bullet} /></li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <div className={`debate-panel__agent-card debate-panel__agent-card--${position.stance}`}>
      <h4 className="debate-panel__agent-label">
        {label} <span className="debate-panel__stance-icon">{icon} {stanceLabel}</span>
      </h4>
      <ul className="debate-panel__reasoning-list">
        {position.reasoning.map((bullet, i) => (
          <li key={i}><Inline text={bullet} /></li>
        ))}
      </ul>
    </div>
  )
}

// "about 2 in 3" for the 0.68 nominal level, else "about N%" with N to the nearest 5, so a retrain at
// another level cannot leave a wrong sentence behind.
function coveragePhrase(coverage) {
  if (Math.abs(coverage - 0.68) < 0.005) return 'about 2 in 3'
  return `about ${Math.round((coverage * 100) / 5) * 5}%`
}

// A size, not a direction or a forecast; coverage is stated, or said to be unmeasured (Rule 4).
function rangeLineText(result) {
  const note = result.range_coverage == null
    ? 'coverage not established for this stock'
    : `${coveragePhrase(result.range_coverage)} recent 5-session moves stayed within this range`
  return `Typical 5-session move: ±${result.range_5s_pct.toFixed(1)}% (${note})`
}

function DataDateLine({ result }) {
  if (!result.data_as_of) return null
  return <p className="debate-panel__data-date">{dataDateText(result)}</p>
}

function VerdictBadge({ verdict }) {
  return (
    <span className={`debate-panel__verdict-badge ${VERDICT_CONFIG[verdict]?.className ?? ''}`}>
      {VERDICT_CONFIG[verdict]?.label ?? 'Unrecognised verdict'}
    </span>
  )
}

// A refusal (ineligible data) or an abstention (fewer than two live agents).
// No stance row, range or reasoning: there is no verdict to explain.
function InsufficientDataState({ result }) {
  const reasons = result.eligibility?.reasons ?? []
  const degraded = result.agents_degraded ?? []
  return (
    <div className="debate-panel__insufficient">
      <div className="debate-panel__verdict-row">
        <VerdictBadge verdict={result.verdict} />
      </div>
      <DataDateLine result={result} />
      {reasons.length > 0 ? (
        <ul className="debate-panel__reason-list">
          {reasons.map(reason => (
            <li key={reason}>{reasonSentence(reason, result.data_age_sessions)}</li>
          ))}
        </ul>
      ) : (
        <>
          <p className="debate-panel__message">Fewer than two agents produced a usable position.</p>
          <ul className="debate-panel__reason-list">
            {degraded.map(id => (
              <li key={id}>{`${agentLabel(id)} — ${degradedText(result.round2[id] ?? {})}`}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function Level2Content({ result }) {
  return (
    <div className="debate-panel__level2">
      <p className="debate-panel__lm-note">{LM_NOTE}</p>
      <div className="debate-panel__agent-cards">
        {Object.entries(result.round2).map(([id, pos]) => (
          <AgentCard key={id} agentId={id} position={pos} />
        ))}
      </div>
      <div className="debate-panel__key-tension">
        <h4 className="debate-panel__section-label">Key Tension</h4>
        {/* null: the call failed or its reply was unusable; no text stands in for it. */}
        {result.synthesis.key_tension
          ? <p><Inline text={result.synthesis.key_tension} /></p>
          : <p className="debate-panel__muted">Key tension unavailable</p>}
      </div>
    </div>
  )
}

function Level3Content({ result }) {
  return (
    <div className="debate-panel__level3">
      <p className="debate-panel__lm-note">{LM_NOTE}</p>
      <h4 className="debate-panel__section-label">Round 1 — Initial Positions</h4>
      {Object.entries(result.round1).map(([id, pos]) => (
        <AgentCard key={id} agentId={id} position={pos} />
      ))}

      <h4 className="debate-panel__section-label">Round 2 — Responses</h4>
      {Object.entries(result.round2).map(([id, pos]) => (
        <AgentCard key={id} agentId={id} position={pos} />
      ))}

      <h4 className="debate-panel__section-label">Synthesis</h4>
      <p className="debate-panel__synthesis-text"><Inline text={result.synthesis.reasoning} /></p>

      {/* Only when the server says it saved it, under the name it gives (older servers send neither). */}
      {result.report_saved === true && result.report_file && (
        <p className="debate-panel__export-note">
          Report saved to <code>reports/{result.report_file}</code>
        </p>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ #
// Main component
// ------------------------------------------------------------------ #

function DebateResultView({ result, level, setLevel }) {
  if (result.verdict === 'INSUFFICIENT_DATA') return <InsufficientDataState result={result} />

  return (
    <>
      {/* Level 1: verdict + stance summary */}
      <div className="debate-panel__level1">
        <div className="debate-panel__verdict-row">
          <VerdictBadge verdict={result.verdict} />
        </div>
        <DataDateLine result={result} />
        <p className="debate-panel__agreement">{agreementText(result)}</p>
        {result.range_5s_pct != null && (
          <p className="debate-panel__vol-range">{rangeLineText(result)}</p>
        )}
        <StanceRow round2={result.round2} />

        <button
          type="button"
          className="debate-panel__toggle"
          onClick={() => setLevel(l => l === 1 ? 2 : 1)}
          aria-expanded={level >= 2}
        >
          {level >= 2 ? 'Hide reasoning' : 'Show reasoning'}
        </button>
      </div>

      {/* Level 2: agent cards + key tension */}
      {level >= 2 && <Level2Content result={result} />}

      {/* Level 2 → Level 3 toggle */}
      {level >= 2 && (
        <button
          type="button"
          className="debate-panel__toggle debate-panel__toggle--secondary"
          onClick={() => setLevel(l => l === 2 ? 3 : 2)}
          aria-expanded={level >= 3}
        >
          {level >= 3 ? 'Hide full debate' : 'Full debate'}
        </button>
      )}

      {/* Level 3: full transcript */}
      {level >= 3 && <Level3Content result={result} />}
    </>
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

// The stage label comes from the server (progress poll), never from a timer; the elapsed
// time is counted here. Until the first poll answers, the first stage's label stands in.
function RunningState({ stage, startedAt }) {
  const elapsed = useElapsedSeconds(startedAt)
  return (
    <div className="debate-panel__loading">
      <span className="debate-panel__spinner" aria-hidden="true" />
      <p className="debate-panel__loading-text" role="status">{STAGE_LABELS[stage] ?? STAGE_LABELS.round1}</p>
      <span className="debate-panel__elapsed">{elapsed} s</span>
    </div>
  )
}

function FailureNotice({ error, ticker, onRetry }) {
  const { message, detail, retry } = describeFailure(error, ticker)
  return (
    <div className="debate-panel__error" role="alert">
      <p className="debate-panel__message debate-panel__message--error">{message}</p>
      {detail && <p className="debate-panel__message">{detail}</p>}
      {retry && (
        <button type="button" className="debate-panel__analyse-button" onClick={onRetry}>
          {retry}
        </button>
      )}
    </div>
  )
}

/**
 * DebatePanel — three-level progressive disclosure for the multi-agent debate.
 *
 * Level 0: not-run state — "Analyse" button + disclaimer
 * Running: the server's stage and the elapsed seconds (a run takes tens of seconds; see README)
 * Level 1: verdict + stance summary + disclaimer (always visible after run)
 * Level 2: agent cards + key tension (expandable)
 * Level 3: full round transcript + synthesis + export note (expandable)
 *
 * The last result per ticker is kept for the session and a run survives a ticker switch: both
 * live in useDebateAnalysis's caches, and App keys this panel by ticker so its disclosure level
 * starts again for each ticker. A failed run shows its reason above any kept result.
 *
 * Rule 6: disclaimer visible in ALL states, never collapsed.
 * Rule 5: agent labels use "Technical Signal", "News Context", "Macro".
 */
export function DebatePanel({ ticker }) {
  const { analyse, isPending, startedAt, result, completedAt, error } = useDebateAnalysis(ticker)
  const progress = useDebateProgress(ticker, startedAt)
  const [level, setLevel] = useState(1)  // 1=verdict, 2=reasoning, 3=full

  const isNotRun = !isPending && !result && !error

  function handleAnalyse() {
    setLevel(1)
    analyse()
  }

  return (
    <section
      className="debate-panel"
      aria-label={ticker ? `Debate analysis for ${ticker}` : 'Debate analysis'}
    >
      {/* Not-run state */}
      {isNotRun && (
        <div className="debate-panel__not-run">
          {ticker ? (
            <button
              type="button"
              className="debate-panel__analyse-button"
              onClick={handleAnalyse}
            >
              Analyse {ticker}
            </button>
          ) : (
            <p className="debate-panel__message">Select a ticker to run debate analysis.</p>
          )}
        </div>
      )}

      {/* Running state: the stage the server reports, and the time spent */}
      {isPending && <RunningState stage={progress.data?.stage} startedAt={startedAt} />}

      {/* A failed run, above any kept result */}
      {!isPending && error && <FailureNotice error={error} ticker={ticker} onRetry={handleAnalyse} />}

      {/* Populated state — Level 1+ (the kept result is not shown as if current while a re-run is going) */}
      {!isPending && result && (
        <div className="debate-panel__populated">
          {completedAt != null && (
            <p className="debate-panel__data-date">Analysed {formatClock(completedAt)}</p>
          )}
          <DebateResultView result={result} level={level} setLevel={setLevel} />

          {/* Re-run button */}
          <button
            type="button"
            className="debate-panel__analyse-button debate-panel__analyse-button--rerun"
            onClick={handleAnalyse}
          >
            Re-analyse {ticker}
          </button>
        </div>
      )}

      {/* Rule 6: inline disclaimer always visible, all states; the full text is one step away */}
      <p className="debate-panel__disclaimer">{INLINE_DISCLAIMER}</p>
      <details className="debate-panel__about">
        <summary>About this analysis</summary>
        <p>{FULL_DISCLAIMER}</p>
      </details>
    </section>
  )
}
