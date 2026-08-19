import { useLayoutEffect, useRef, useState } from 'react'
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

// Rule 5's technical basis is a fixed list, hardcoded on the backend
// (`_compute_sentiment`'s `inputs = ["RSI", "MACD", "Ichimoku position"]`)
// — unlike Confidence's basis (genuinely depends on whether this specific
// ticker has backtest history) or Advice's reasoning (depends on this
// ticker's own predicted move vs. its volatility), this text never
// varies per ticker or needs real data to be correct. It's rendered
// unconditionally below, including before any ticker is selected, so it
// doesn't need to blank out and reappear on every ticker switch either.
const SENTIMENT_BASIS_TEXT = 'RSI, MACD, Ichimoku position — not news or market sentiment'

// Per-ticker remembered populated height (module-level, survives remounts —
// selecting a ticker doesn't unmount AIInsightPanel, but this is cheap
// insurance and lets a fresh mount already know a previously-seen ticker's
// height). Guessing skeleton bar heights to match real rendered text proved
// fragile — subtext/reasoning wrap to 1 or 2 lines depending on the ticker,
// the backtest button adds height on the N/A-confidence branch, and
// near_gap tickers have no Advice block at all — so instead of matching
// shape, this remembers each ticker's own last real height and holds the
// card at that height while its next fetch is in flight.
const rememberedHeights = new Map()

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
  const sectionRef = useRef(null)
  const prevTickerRef = useRef(ticker)
  const [minHeight, setMinHeight] = useState(() => rememberedHeights.get(ticker) ?? null)

  // Adopt this ticker's remembered height the instant `ticker` changes —
  // done synchronously during render (the "derive state from a changed
  // prop" pattern), not in a useEffect. AIInsightPanel doesn't unmount
  // between ticker switches (same instance, `ticker` prop just changes),
  // so useState's initializer never re-runs on switch, and a plain
  // useEffect fires only after React has already painted one frame with
  // the *previous* ticker's minHeight still applied — exactly the
  // one-frame flash this is meant to prevent. Updating state mid-render
  // like this is a documented React escape hatch for precisely this case.
  //
  // Deliberately does NOT fall back to the *previous* ticker's remembered
  // height when this ticker has never been seen before (an earlier version
  // did, reasoning it was "a reasonable floor" versus the skeleton's
  // shorter natural height) — measured live, that fallback is exactly
  // backwards. Two tickers' populated layouts differ in item count/subtext
  // wrapping/backtest-button presence, so borrowing an unrelated ticker's
  // height as a loading-state floor just relocates the jump: the loading
  // skeleton renders at the wrong height, then still snaps once real data
  // lands and the min-height is dropped. This is most visible right after
  // a page reload, when `rememberedHeights` is empty and *every* first
  // click of any ticker hits this path. `null` here means the loading
  // skeleton renders at its own natural (always-3-item, always-consistent)
  // height instead — visually stable across the loading -> populated
  // transition for a ticker that's never been measured yet.
  if (prevTickerRef.current !== ticker) {
    prevTickerRef.current = ticker
    setMinHeight(rememberedHeights.get(ticker) ?? null)
  }

  const notLoaded =
    insightQuery.isError && insightQuery.error instanceof ApiError && insightQuery.error.status === 404
  const featureFailure =
    insightQuery.isError &&
    insightQuery.error instanceof ApiError &&
    typeof insightQuery.error.status === 'number' &&
    insightQuery.error.status >= 500
  const genericError = insightQuery.isError && !notLoaded && !featureFailure
  const isPopulated = Boolean(ticker) && !insightQuery.isLoading && !notLoaded && !featureFailure && !genericError

  // After every populated render, measure the real height and remember it
  // for this ticker — runs before paint (useLayoutEffect) so a height
  // that's already correct doesn't cause a visible one-frame jump.
  useLayoutEffect(() => {
    if (!isPopulated || !sectionRef.current) return
    const height = sectionRef.current.getBoundingClientRect().height
    rememberedHeights.set(ticker, height)
    setMinHeight(height)
  })

  // The outer <section> is rendered once, unconditionally, for every state
  // below (loading/not-loaded/failed/error/populated) — only its inner
  // content swaps. This mirrors PredictionDisplay's structure and avoids
  // the panel's whole card shape (and the taller populated layout beside
  // it) collapsing to a single centered line and back on every ticker
  // switch, which read as a jarring flash/reflow (reported after the
  // Decision 1-12 polish pass shipped).
  let content = null

  if (!ticker || insightQuery.isLoading) {
    // No ticker selected yet, OR a ticker's insight is in flight
    // (design.md Decision 13, twice revised — see Decision 13's
    // correction notes for the flicker/geometry fixes this shape already
    // went through). "Confidence"/"Technical Signal"/"Advice" are static
    // section titles, not data — they render as real text immediately and
    // never change across no-ticker -> loading -> populated, the same way
    // PredictionDisplay's "Prediction" <h2> never changes. Only each
    // item's VALUE (and subtext/reasoning) is the actual placeholder here,
    // via `N/A` and the existing `--placeholder` classes — that's the
    // part that's genuinely still loading. `N/A` (not a dash) so the
    // placeholder renders at the same visual weight as a real value in
    // the same font-size/family/weight, distinguished from a real result
    // only by the muted `--placeholder` color — a dash technically
    // matched font-size too but read as much smaller/less substantial
    // than real content purely because a single dash glyph has far less
    // visual bulk than a real value string. Confidence's real N/A state
    // (no backtest history for a selected ticker, `--na` class) uses the
    // same word but a distinctly more legible color — the two stay
    // visually distinct by shade, not by wording.
    //
    // The "real label = real data has loaded" invariant this file
    // previously used (tests/assistive tech waiting for the label text
    // itself to appear) no longer holds, since the label is now always
    // present — anything that needs to detect "data has loaded" must wait
    // on a VALUE instead (e.g. `findByText('Bullish')`, not
    // `findByText('Technical Signal')`). The `sr-only` announcement below
    // is still the loading signal for screen readers.
    content = (
      <>
        <span className="ai-insight-panel__sr-only">
          {ticker ? `Loading AI insight for ${ticker}…` : 'AI insight'}
        </span>
        <div className="ai-insight-panel__item">
          <h3 className="ai-insight-panel__label">Confidence</h3>
          <p className="ai-insight-panel__value ai-insight-panel__value--placeholder" aria-hidden="true">
            N/A
          </p>
          <p className="ai-insight-panel__subtext" aria-hidden="true">
            &nbsp;
          </p>
        </div>
        <div className="ai-insight-panel__item">
          <h3 className="ai-insight-panel__label">Technical Signal</h3>
          <p className="ai-insight-panel__value ai-insight-panel__value--placeholder" aria-hidden="true">
            N/A
          </p>
          {/* Real text, not aria-hidden and not blanked to &nbsp; like the
              two placeholders above/below — SENTIMENT_BASIS_TEXT is fixed
              regardless of ticker or load state, so there's real content
              a screen reader should hear now, the same reasoning already
              applied to the disclaimer below. */}
          <p className="ai-insight-panel__subtext">{SENTIMENT_BASIS_TEXT}</p>
        </div>
        <div className="ai-insight-panel__item">
          <h3 className="ai-insight-panel__label">Advice</h3>
          <p className="ai-insight-panel__reasoning" aria-hidden="true">
            &nbsp;
          </p>
          <p className="ai-insight-panel__value ai-insight-panel__value--placeholder" aria-hidden="true">
            N/A
          </p>
        </div>
        {/* Not aria-hidden — the disclaimer's text is real, unconditional
            content (Rule 6) that never changes between loading and
            populated, so a screen-reader user should hear it now rather
            than wait for real data. */}
        <p className="ai-insight-panel__disclaimer">{INLINE_DISCLAIMER}</p>
      </>
    )
  } else if (notLoaded) {
    content = (
      <p className="ai-insight-panel__message">
        {ticker} hasn't been loaded yet. Load it from the ticker panel to see its AI insight.
      </p>
    )
  } else if (featureFailure) {
    content = (
      <p className="ai-insight-panel__message ai-insight-panel__message--error" role="alert">
        Feature computation failed for {ticker}. Try again later.
      </p>
    )
  } else if (genericError) {
    content = (
      <p className="ai-insight-panel__message ai-insight-panel__message--error" role="alert">
        Couldn't load AI insight for {ticker} — please try again.
      </p>
    )
  } else {
    const insight = insightQuery.data
    const sentimentLabel = SENTIMENT_LABEL[insight.sentiment_proxy] ?? insight.sentiment_proxy
    const advice = insight.advice_text ? ADVICE_COPY[insight.advice_text] : null

    content = (
      <>
        {/* Confidence — Rule 4: real hit-rate when it exists, explicit N/A
            (never a fabricated/pooled substitute) otherwise. */}
        <div className="ai-insight-panel__item" data-item="confidence">
          <h3 className="ai-insight-panel__label">Confidence</h3>
          {insight.confidence_score != null ? (
            <>
              <p className="ai-insight-panel__value ai-insight-panel__value--numeric">
                {Math.round(insight.confidence_score * 100)}%
              </p>
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
            {(insight.sentiment_inputs ?? []).join(', ')} — not news or market sentiment
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
      </>
    )
  }

  return (
    <section
      ref={sectionRef}
      className="ai-insight-panel"
      aria-label={ticker ? `AI insight for ${ticker}` : 'AI insight'}
      style={!isPopulated && minHeight ? { minHeight } : undefined}
    >
      {content}
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
