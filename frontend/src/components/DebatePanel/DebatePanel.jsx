import { useState } from 'react'
import { useDebateAnalysis } from '../../hooks/useDebateAnalysis'
import { ApiError } from '../../api/client'
import './debate-panel.css'

// ------------------------------------------------------------------ #
// Constants
// ------------------------------------------------------------------ #

const INLINE_DISCLAIMER =
  'Technical observation — not investment advice. See docs/DISCLAIMER.md.'

// Verdict display config
const VERDICT_CONFIG = {
  STRONG_BUY_SIGNAL:      { label: 'Strong Buy Signal',      className: 'debate-panel__verdict--strong-bull' },
  BUY_SIGNAL:             { label: 'Buy Signal',              className: 'debate-panel__verdict--bull' },
  OBSERVE:                { label: 'Observe',                 className: 'debate-panel__verdict--neutral' },
  CAUTION_SIGNAL:         { label: 'Caution Signal',          className: 'debate-panel__verdict--bear' },
  STRONG_CAUTION_SIGNAL:  { label: 'Strong Caution Signal',   className: 'debate-panel__verdict--strong-bear' },
  SPLIT:                  { label: 'Split — No Consensus',    className: 'debate-panel__verdict--split' },
}

const STANCE_ICONS = { bull: '↑', neutral: '→', bear: '↓' }
const STANCE_LABELS = { bull: 'Bullish', neutral: 'Neutral', bear: 'Bearish' }

// Agent labels — Rule 5: TechnicalAgent = "Technical Signal", NewsAgent = "News Context"
const AGENT_LABELS = {
  technical: 'Technical Signal',
  news: 'News Context',
  macro: 'Macro',
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

function agreementText(result) {
  const { agreement_level, round2 } = result
  const stances = Object.values(round2).map(p => p.stance)
  const majority = stances.reduce((acc, s) => { acc[s] = (acc[s] || 0) + 1; return acc }, {})
  const topStance = Object.entries(majority).sort((a, b) => b[1] - a[1])[0]
  const n = topStance ? topStance[1] : 0
  if (agreement_level === 'split') return 'Split — 3 different positions'
  return `${agreement_level.charAt(0).toUpperCase() + agreement_level.slice(1)} — ${n} of 3 agents`
}

// ------------------------------------------------------------------ #
// Sub-components
// ------------------------------------------------------------------ #

function StanceRow({ round2 }) {
  return (
    <div className="debate-panel__stance-row">
      {Object.entries(round2).map(([id, pos]) => (
        <span key={id} className={`debate-panel__stance-chip debate-panel__stance-chip--${pos.stance}`}>
          {agentLabel(id)} {stanceIcon(pos.stance)}
        </span>
      ))}
    </div>
  )
}

function AgentCard({ agentId, position }) {
  const label = agentLabel(agentId)
  const icon = stanceIcon(position.stance)
  const stanceLabel = STANCE_LABELS[position.stance] ?? position.stance

  return (
    <div className={`debate-panel__agent-card debate-panel__agent-card--${position.stance}`}>
      <h4 className="debate-panel__agent-label">
        {label} <span className="debate-panel__stance-icon">{icon} {stanceLabel}</span>
      </h4>
      <ul className="debate-panel__reasoning-list">
        {position.reasoning.map((bullet, i) => (
          <li key={i}>{bullet}</li>
        ))}
      </ul>
    </div>
  )
}

function Level2Content({ result }) {
  return (
    <div className="debate-panel__level2">
      <div className="debate-panel__agent-cards">
        {Object.entries(result.round2).map(([id, pos]) => (
          <AgentCard key={id} agentId={id} position={pos} />
        ))}
      </div>
      <div className="debate-panel__key-tension">
        <h4 className="debate-panel__section-label">Key Tension</h4>
        <p>{result.synthesis.key_tension}</p>
      </div>
    </div>
  )
}

function Level3Content({ result }) {
  return (
    <div className="debate-panel__level3">
      <h4 className="debate-panel__section-label">Round 1 — Initial Positions</h4>
      {Object.entries(result.round1).map(([id, pos]) => (
        <AgentCard key={id} agentId={id} position={pos} />
      ))}

      <h4 className="debate-panel__section-label">Round 2 — Responses</h4>
      {Object.entries(result.round2).map(([id, pos]) => (
        <AgentCard key={id} agentId={id} position={pos} />
      ))}

      <h4 className="debate-panel__section-label">Synthesis</h4>
      <p className="debate-panel__synthesis-text">{result.synthesis.reasoning}</p>

      <p className="debate-panel__export-note">
        Report saved to <code>reports/{result.as_of}_{result.ticker}.md</code>
      </p>
    </div>
  )
}

// ------------------------------------------------------------------ #
// Main component
// ------------------------------------------------------------------ #

/**
 * DebatePanel — three-level progressive disclosure for the multi-agent debate.
 *
 * Level 0: not-run state — "Analyse" button + disclaimer
 * Level 1: verdict + stance summary + disclaimer (always visible after run)
 * Level 2: agent cards + key tension (expandable)
 * Level 3: full round transcript + synthesis + export note (expandable)
 *
 * Feature flag: only rendered when VITE_DEBATE_PANEL_ENABLED=true.
 * Rule 6: disclaimer visible in ALL states, never collapsed.
 * Rule 5: agent labels use "Technical Signal", "News Context", "Macro".
 */
export function DebatePanel({ ticker }) {
  const mutation = useDebateAnalysis(ticker)
  const [level, setLevel] = useState(1)  // 1=verdict, 2=reasoning, 3=full

  // Reset level when ticker changes
  const [lastTicker, setLastTicker] = useState(ticker)
  if (ticker !== lastTicker) {
    setLastTicker(ticker)
    mutation.reset()
    setLevel(1)
  }

  const result = mutation.data
  const isNotRun = !mutation.isPending && !mutation.isSuccess && !mutation.isError
  const isError = mutation.isError
  const notLoaded = isError && mutation.error instanceof ApiError && mutation.error.status === 404

  // ---- Loading stage label ----
  // The backend debate takes 4-8s. We approximate stage progress by elapsed time.
  const [startTime] = useState(null)

  function handleAnalyse() {
    setLevel(1)
    mutation.mutate()
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

      {/* Loading state */}
      {mutation.isPending && (
        <div className="debate-panel__loading" aria-live="polite">
          <span className="debate-panel__spinner" aria-hidden="true" />
          <p className="debate-panel__loading-text">Running agents…</p>
        </div>
      )}

      {/* Error states */}
      {notLoaded && (
        <p className="debate-panel__message debate-panel__message--error" role="alert">
          {ticker} hasn't been loaded yet. Load it from the ticker panel first.
        </p>
      )}
      {isError && !notLoaded && (
        <div className="debate-panel__error" role="alert">
          <p className="debate-panel__message debate-panel__message--error">
            Analysis failed — please try again.
          </p>
          <button type="button" className="debate-panel__analyse-button" onClick={handleAnalyse}>
            Retry
          </button>
        </div>
      )}

      {/* Populated state — Level 1+ */}
      {mutation.isSuccess && result && (
        <div className="debate-panel__populated">
          {/* Level 1: verdict + stance summary */}
          <div className="debate-panel__level1">
            <div className="debate-panel__verdict-row">
              <span
                className={`debate-panel__verdict-badge ${VERDICT_CONFIG[result.verdict]?.className ?? ''}`}
              >
                {VERDICT_CONFIG[result.verdict]?.label ?? result.verdict}
              </span>
            </div>
            <p className="debate-panel__agreement">{agreementText(result)}</p>
            {result.volatility_range_pct != null && (
              <p className="debate-panel__vol-range">
                Expected range: ±{result.volatility_range_pct.toFixed(2)}% (5 sessions)
              </p>
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

      {/* Rule 6: disclaimer always visible, all states, no collapse */}
      <p className="debate-panel__disclaimer">{INLINE_DISCLAIMER}</p>
    </section>
  )
}
