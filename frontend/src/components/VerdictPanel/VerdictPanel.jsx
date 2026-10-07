import { useDebateProgress } from '../../hooks/useDebateProgress'
import { useTickerContext } from '../../hooks/useTickerContext'
import { FULL_DISCLAIMER, INLINE_DISCLAIMER } from '../../lib/disclaimer'
import { chooseVerdictState } from '../../lib/verdictState'
import { RangeBlock } from './RangeBlock'
import { ResultBody } from './VerdictParts'
import { FailureNotice, InsufficientBody, ReadyBody, RunningState } from './PanelStates'
import './verdict-panel.css'

/**
 * The Verdict panel: the typical 5-session move and its range check at the top (the range block, here
 * or, on a phone, above the chart: `showRange`), then one of six states chosen by `chooseVerdictState`
 * from the ticker's eligibility and the run's status: ready, running, result, one agent unavailable,
 * insufficient data and failed (a kept result stays beneath the error). With no ticker it asks for one.
 *
 * It reads the run it is given: `useDebateAnalysis` is called once, in the workspace, and the panel and
 * the Debate matrix both read that one run and its kept result. The server's stage comes from the
 * progress poll.
 *
 * Rule 6: the disclaimer is visible in every state, never collapsible, with the full text one step away.
 * Rule 5: agent labels name what each agent reads; language-model text is marked as such.
 *
 * @param {{ticker: string|null, analysis: object, showRange?: boolean}} props
 */
export function VerdictPanel({ ticker, analysis, showRange = true }) {
  const { analyse, isPending, startedAt, result, completedAt, error } = analysis
  const context = useTickerContext(ticker)
  const progress = useDebateProgress(ticker, startedAt)

  const eligibility =
    context.eligible === null
      ? null
      : { eligible: context.eligible, reasons: context.reasons, age_sessions: context.ageSessions }
  const state = chooseVerdictState({ ticker, run: { isPending, error }, result, eligibility, range: null })

  // A kept result shows for a finished run, and beneath the error of a failed re-run.
  const kept = Boolean(result) && state !== 'running' && state !== 'ready' && state !== 'none'
  const keptInsufficient = kept && result.verdict === 'INSUFFICIENT_DATA'

  return (
    <aside className="verdict-panel" aria-label="Verdict" data-state={state}>
      {showRange ? <RangeBlock ticker={ticker} /> : null}

      <div className="verdict-panel__body">
        {state === 'none' && <p className="verdict-panel__meta t-body">Select a ticker to run debate analysis.</p>}
        {state === 'ready' && <ReadyBody ticker={ticker} onAnalyse={analyse} />}
        {state === 'running' && <RunningState stage={progress.data?.stage} startedAt={startedAt} />}
        {state === 'failed' && <FailureNotice error={error} ticker={ticker} onRetry={analyse} />}
        {kept && !keptInsufficient && (
          <ResultBody ticker={ticker} result={result} completedAt={completedAt} onAnalyse={analyse} />
        )}
        {(keptInsufficient || (state === 'insufficient' && !result)) && (
          <InsufficientBody
            ticker={ticker}
            result={keptInsufficient ? result : null}
            context={context}
            canReanalyse={Boolean(result) && context.eligible !== false}
            onAnalyse={analyse}
          />
        )}
      </div>

      {/* Rule 6: inline disclaimer always visible, in every state; the full text is one step away. */}
      <div className="verdict-panel__foot">
        <p className="verdict-panel__disclaimer t-small">{INLINE_DISCLAIMER}</p>
        <details className="verdict-panel__about t-small">
          <summary>About this analysis</summary>
          <p>{FULL_DISCLAIMER}</p>
        </details>
      </div>
    </aside>
  )
}
