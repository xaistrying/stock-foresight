import { useTickerPrediction } from '../../hooks/useTickerPrediction'
import { logReturnToPercent } from '../../lib/logReturn'
import { ApiError } from '../../api/client'
import './prediction-display.css'

/**
 * Prediction display (tasks.md section 9): consumes `GET
 * /tickers/{ticker}/prediction` for the selected ticker and renders four
 * visually distinct states — `status: "ok"`, `status: "near_gap"`, 404
 * (not-loaded), 5xx (feature computation failed) — sharing no generic/blank
 * treatment across more than one of them (dashboard-ui spec, 9.3).
 *
 * The raw `predicted_log_return` never reaches this render path — it's
 * converted via the shared `logReturnToPercent` utility (9.2, Rule 2)
 * before display, the same conversion the chart panel's single point uses.
 */
export function PredictionDisplay({ ticker }) {
  const predictionQuery = useTickerPrediction(ticker)

  const notLoaded =
    predictionQuery.isError &&
    predictionQuery.error instanceof ApiError &&
    predictionQuery.error.status === 404
  const featureFailure =
    predictionQuery.isError &&
    predictionQuery.error instanceof ApiError &&
    typeof predictionQuery.error.status === 'number' &&
    predictionQuery.error.status >= 500
  const genericError = predictionQuery.isError && !notLoaded && !featureFailure

  let state = null
  if (!ticker) {
    // No ticker selected yet (design.md Decision 13, wording later revised
    // to "N/A" — see prediction-display.css): render the title plus an
    // explicit N/A placeholder in place of the percent/as-of/horizon
    // block, instead of unmounting — keeps the dashboard's shape stable
    // at all times, matching AIInsightPanel's equivalent no-ticker state.
    // N/A renders at the same font-size/family/weight as a real
    // percentage (only color differs, via --percent--placeholder), so it
    // reads as visually substantial rather than a barely-visible dash.
    state = { kind: 'no-ticker' }
  } else if (predictionQuery.isLoading) {
    state = { kind: 'loading', message: 'Loading prediction…' }
  } else if (notLoaded) {
    state = {
      kind: 'not-loaded',
      message: `${ticker} hasn't been loaded yet. Load it from the ticker panel to see a prediction.`,
    }
  } else if (featureFailure) {
    state = {
      kind: 'failed',
      message: `Feature computation failed for ${ticker}. Try again later.`,
    }
  } else if (genericError) {
    state = { kind: 'error', message: `Couldn't load the prediction for ${ticker} — please try again.` }
  } else if (predictionQuery.data?.status === 'near_gap') {
    state = {
      kind: 'near-gap',
      message: `A data gap near ${ticker}'s most recent sessions prevents a current prediction.`,
    }
  } else if (predictionQuery.data?.status === 'ok') {
    const percent = logReturnToPercent(predictionQuery.data.predicted_log_return)
    state = {
      kind: 'ok',
      percent,
      asOf: predictionQuery.data.as_of,
    }
  }

  return (
    <section className="prediction-display" aria-label={ticker ? `Prediction for ${ticker}` : 'Prediction'}>
      <h2 className="prediction-display__title">Prediction</h2>
      {state?.kind === 'ok' ? (
        <div className="prediction-display__result" data-kind="ok">
          <p
            className="prediction-display__percent"
            data-direction={state.percent >= 0 ? 'up' : 'down'}
          >
            {state.percent >= 0 ? '+' : ''}
            {state.percent.toFixed(2)}%
          </p>
          <p className="prediction-display__as-of">As of {state.asOf}</p>
          <p className="prediction-display__horizon">Fixed horizon: 5 trading sessions</p>
        </div>
      ) : state?.kind === 'no-ticker' ? (
        <div className="prediction-display__result" data-kind="no-ticker">
          <p className="prediction-display__percent prediction-display__percent--placeholder">N/A</p>
          {/* Same three-line shape as the 'ok' branch above (percent +
              as-of + horizon), not just the percent — otherwise selecting
              a ticker for the first time grows the card by two lines,
              the exact kind of layout jump the dash/N/A placeholder was
              introduced to avoid in the first place. The horizon line
              isn't ticker-dependent (Rule 1's 5-session horizon is fixed
              regardless of selection) so it renders unconditionally,
              identical to the populated state; only "As of" needs its
              own placeholder since there's no real date yet. */}
          <p className="prediction-display__as-of">As of —</p>
          <p className="prediction-display__horizon">Fixed horizon: 5 trading sessions</p>
        </div>
      ) : (
        state && (
          <div
            className="prediction-display__state"
            data-kind={state.kind}
            role={state.kind === 'error' || state.kind === 'failed' ? 'alert' : undefined}
          >
            {state.kind === 'loading' && <span className="prediction-display__spinner" aria-hidden="true" />}
            <p className="prediction-display__message">{state.message}</p>
          </div>
        )
      )}
    </section>
  )
}
