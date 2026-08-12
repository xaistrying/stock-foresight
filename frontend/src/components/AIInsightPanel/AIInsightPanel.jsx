import { useTickerInsight } from '../../hooks/useTickerInsight'
import { useBacktestTicker } from '../../hooks/useBacktestTicker'
import { ApiError } from '../../api/client'
import './ai-insight-panel.css'

// Advice copy contract (docs/M5_DASHBOARD_EXPLORE_NOTES.md's "Copy contract"
// section) — `advice_text` from `GET /tickers/{ticker}/insight` is one of
// "HOLD" / "up" / "down" (never "BUY"/"SELL", Rules 3/6). Each verdict is
// preceded by the reasoning line that produced it, never shown standalone.
const ADVICE_COPY = {
  HOLD: { reasoning: 'Move is within normal volatility range', verdict: 'HOLD' },
  up: { reasoning: 'Move exceeds typical volatility to the upside', verdict: 'Signal: up' },
  down: { reasoning: 'Move exceeds typical volatility to the downside', verdict: 'Signal: down' },
}

// Sentiment label casing (backend sends lowercase bullish/bearish/neutral,
// Rule 5's "Technical Signal" wording is applied entirely at this layer).
const SENTIMENT_LABEL = {
  bullish: 'Bullish',
  bearish: 'Bearish',
  neutral: 'Neutral',
}

const INLINE_DISCLAIMER =
  'Technical observation from a backtested model — not a forecast, not investment advice.'

/**
 * AI insight panel (tasks.md section 10): Confidence, Sentiment ("Technical
 * Signal"), and Advice for the selected ticker, consuming `GET
 * /tickers/{ticker}/insight` — plus the unconditional disclaimer (Rule 6).
 * Not a placeholder; renders real computed values for any loaded ticker
 * (dashboard-ui spec: "AI insight panel renders for any loaded ticker").
 */
export function AIInsightPanel({ ticker }) {
  const insightQuery = useTickerInsight(ticker)
  const backtestMutation = useBacktestTicker(ticker)

  const notLoaded =
    insightQuery.isError && insightQuery.error instanceof ApiError && insightQuery.error.status === 404
  const featureFailure =
    insightQuery.isError &&
    insightQuery.error instanceof ApiError &&
    typeof insightQuery.error.status === 'number' &&
    insightQuery.error.status >= 500
  const genericError = insightQuery.isError && !notLoaded && !featureFailure

  if (!ticker) {
    return (
      <section className="ai-insight-panel" aria-label="AI insight">
        <p className="ai-insight-panel__message">Select a ticker to see its AI insight.</p>
      </section>
    )
  }

  if (insightQuery.isLoading) {
    return (
      <section className="ai-insight-panel" aria-label={`AI insight for ${ticker}`}>
        <div className="ai-insight-panel__state">
          <span className="ai-insight-panel__spinner" aria-hidden="true" />
          <p className="ai-insight-panel__message">Loading AI insight…</p>
        </div>
      </section>
    )
  }

  if (notLoaded) {
    return (
      <section className="ai-insight-panel" aria-label={`AI insight for ${ticker}`}>
        <p className="ai-insight-panel__message">
          {ticker} hasn't been loaded yet. Load it from the ticker panel to see its AI insight.
        </p>
      </section>
    )
  }

  if (featureFailure) {
    return (
      <section className="ai-insight-panel" aria-label={`AI insight for ${ticker}`}>
        <p className="ai-insight-panel__message ai-insight-panel__message--error" role="alert">
          Feature computation failed for {ticker}. Try again later.
        </p>
      </section>
    )
  }

  if (genericError) {
    return (
      <section className="ai-insight-panel" aria-label={`AI insight for ${ticker}`}>
        <p className="ai-insight-panel__message ai-insight-panel__message--error" role="alert">
          Couldn't load AI insight for {ticker} — please try again.
        </p>
      </section>
    )
  }

  const insight = insightQuery.data
  const sentimentLabel = SENTIMENT_LABEL[insight.sentiment_proxy] ?? insight.sentiment_proxy
  const advice = insight.advice_text ? ADVICE_COPY[insight.advice_text] : null

  return (
    <section className="ai-insight-panel" aria-label={`AI insight for ${ticker}`}>
      {/* Confidence — Rule 4: real hit-rate when it exists, explicit N/A
          (never a fabricated/pooled substitute) otherwise. */}
      <div className="ai-insight-panel__item" data-item="confidence">
        <h3 className="ai-insight-panel__label">Confidence</h3>
        {insight.confidence_score != null ? (
          <>
            <p className="ai-insight-panel__value">{Math.round(insight.confidence_score * 100)}%</p>
            <p className="ai-insight-panel__subtext">{insight.confidence_basis}</p>
          </>
        ) : (
          <>
            <p className="ai-insight-panel__value ai-insight-panel__value--na">N/A</p>
            <p className="ai-insight-panel__subtext">{insight.confidence_basis}</p>
            <BacktestAction ticker={ticker} mutation={backtestMutation} />
          </>
        )}
      </div>

      {/* Sentiment — Rule 5: labeled "Technical Signal", basis always
          visible inline (from the response's own sentiment_inputs, not a
          hardcoded copy of it), never behind a tooltip/hover. */}
      <div className="ai-insight-panel__item" data-item="sentiment">
        <h3 className="ai-insight-panel__label">Technical Signal</h3>
        <p className="ai-insight-panel__value">{sentimentLabel}</p>
        <p className="ai-insight-panel__subtext">
          Based on {(insight.sentiment_inputs ?? []).join(', ')} — not news or market sentiment
        </p>
      </div>

      {/* Advice — Rules 3/6: volatility-relative, directional wording only,
          never rendered for near_gap (advice_text is null there). */}
      {advice && (
        <div className="ai-insight-panel__item" data-item="advice">
          <h3 className="ai-insight-panel__label">Advice</h3>
          <p className="ai-insight-panel__reasoning">{advice.reasoning}</p>
          <p className="ai-insight-panel__value" data-verdict={insight.advice_text}>
            {advice.verdict}
          </p>
        </div>
      )}
      {!advice && insight.note && <p className="ai-insight-panel__note">{insight.note}</p>}

      {/* Disclaimer — Rule 6: unconditional, no toggle/collapse anywhere. */}
      <p className="ai-insight-panel__disclaimer">{INLINE_DISCLAIMER}</p>
    </section>
  )
}

/**
 * "Backtest this ticker" action (tasks.md 10.3). There's no separate
 * read-only gate-check endpoint — `SINGLE_TICKER_BACKTEST_MIN_ROWS` is only
 * enforced inside `POST /backtest` itself, which 409s below the threshold.
 * The action is always offered when Confidence is N/A; clicking it is the
 * threshold check. A 409 renders as "needs more history" explanatory text
 * (matching the spec's "hidden or disabled below threshold" intent) rather
 * than a generic failure, and the button becomes disabled once that's known
 * for this ticker. A non-409 failure shows a distinct retry message.
 */
function BacktestAction({ ticker, mutation }) {
  if (mutation.isSuccess) return null

  if (mutation.isBelowThreshold) {
    return (
      <p className="ai-insight-panel__backtest-note">
        Needs more price history to backtest — check back after more sessions load.
      </p>
    )
  }

  if (mutation.isError) {
    return (
      <div className="ai-insight-panel__backtest">
        <button
          type="button"
          className="ai-insight-panel__backtest-button"
          onClick={() => mutation.mutate()}
        >
          Backtest this ticker
        </button>
        <p className="ai-insight-panel__backtest-note ai-insight-panel__backtest-note--error" role="alert">
          Backtest failed for {ticker} — please try again.
        </p>
      </div>
    )
  }

  return (
    <button
      type="button"
      className="ai-insight-panel__backtest-button"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {mutation.isPending && <span className="ai-insight-panel__spinner" aria-hidden="true" />}
      {mutation.isPending ? 'Backtesting…' : 'Backtest this ticker'}
    </button>
  )
}
