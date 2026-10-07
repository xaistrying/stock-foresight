import { Inline } from '../Inline'
import { LM_NOTE } from '../../lib/disclaimer'
import {
  UNKNOWN_VERDICT,
  VERDICT_CONFIG,
  agentLabel,
  agreementText,
  dataDateText,
  formatClock,
  stanceMark,
} from '../../lib/debateText'

/**
 * The verdict as a badge: the display label from the `debate-synthesiser` table, unchanged, with an
 * arrow glyph before it for a directional lean only. The glyph is its own element hidden from
 * assistive technology, so the badge's accessible text is exactly the label. Direction is never told
 * by hue alone, and the label never reads as an instruction.
 */
export function VerdictBadge({ verdict }) {
  const { label, arrow, tone } = VERDICT_CONFIG[verdict] ?? UNKNOWN_VERDICT
  return (
    <span className={`verdict-badge verdict-badge--${tone}`}>
      {arrow ? (
        <span className="verdict-badge__glyph" aria-hidden="true">
          {arrow}
        </span>
      ) : null}
      {label}
    </span>
  )
}

/** One chip per agent for its Round 2 position: agent, arrow and word. An agent that did not vote says so. */
export function StanceChips({ round2 }) {
  return (
    <div className="verdict-panel__chips">
      {Object.entries(round2).map(([id, position]) =>
        position.degraded_reason ? (
          <span key={id} className="stance-chip stance-chip--unavailable">
            {agentLabel(id)} unavailable
          </span>
        ) : (
          <span key={id} className={`stance-chip stance-chip--${position.stance}`}>
            {agentLabel(id)} {stanceMark(position.stance)}
          </span>
        ),
      )}
    </div>
  )
}

/** The data line: "Data as of 2026-10-02 · 2 sessions old". Nothing for an older payload with no date. */
export function DataLine({ result }) {
  if (!result.data_as_of) return null
  return <p className="verdict-panel__meta t-small">{dataDateText(result)}</p>
}

/**
 * Key tension: the synthesiser's one or two sentences, in the warn colours (the only place they are
 * used), or a plain statement that it is unavailable (the call failed or its reply was unusable; no
 * text stands in for it).
 */
function KeyTension({ text }) {
  return (
    <section className="verdict-panel__tension">
      <h3 className="verdict-panel__tension-label t-label">Key tension</h3>
      {text ? (
        <p className="verdict-panel__tension-text t-body">
          <Inline text={text} />
        </p>
      ) : (
        <p className="verdict-panel__tension-text t-body">Key tension unavailable</p>
      )}
    </section>
  )
}

/**
 * A finished run, in the design's order: badge, Agreement, stance chips, Key tension, Synthesis, the
 * data line, when it was produced, whether a report was saved, and Re-analyse. Nothing is behind a toggle.
 */
export function ResultBody({ ticker, result, completedAt, onAnalyse }) {
  const synthesis = result.synthesis ?? {}
  return (
    <div className="verdict-panel__result">
      <VerdictBadge verdict={result.verdict} />
      <p className="verdict-panel__agreement t-small">{agreementText(result)}</p>
      <StanceChips round2={result.round2} />
      <p className="verdict-panel__lm-note t-small">{LM_NOTE}</p>
      <KeyTension text={synthesis.key_tension} />
      {synthesis.reasoning ? (
        <section className="verdict-panel__synthesis">
          <h3 className="t-heading">Synthesis</h3>
          <p className="t-body">
            <Inline text={synthesis.reasoning} />
          </p>
        </section>
      ) : null}
      <DataLine result={result} />
      {completedAt != null ? <p className="verdict-panel__meta t-small">Analysed {formatClock(completedAt)}</p> : null}
      {/* Only when the server says it saved it, under the name it gives (older servers send neither). */}
      {result.report_saved === true && result.report_file ? (
        <p className="verdict-panel__meta t-small">
          Report saved to <code>reports/{result.report_file}</code>
        </p>
      ) : null}
      <button type="button" className="verdict-panel__button verdict-panel__button--secondary" onClick={onAnalyse}>
        Re-analyse {ticker}
      </button>
    </div>
  )
}
