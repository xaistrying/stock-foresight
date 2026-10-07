import { useTickerRange } from '../../hooks/useTickerRange'
import { ApiError } from '../../api/client'
import { INLINE_DISCLAIMER } from '../../lib/disclaimer'
import './range-display.css'

/**
 * Range display: the typical 5-session move for the selected ticker, from
 * `GET /tickers/{ticker}/range`. It states a size, never a direction: the figure is an unsigned
 * half-width ("±3.2%"), drawn with no up/down colour, and `sigma_daily_pct` (a per-session figure)
 * is never rendered. It is also the only surface that renders the measured range hit-rate.
 *
 * States, each with its own treatment: no ticker (N/A placeholders in the same shape as the
 * populated card, so selecting a ticker does not shift the layout), loading, available,
 * unavailable (200 with no `range_5s_pct`), not loaded (404) and failed (5xx or a network
 * error). "Available" means `range_5s_pct` is a number; `status` and `reasons` are display text
 * only, so a status added later cannot cause a stale figure to be shown.
 *
 * The disclaimer in force is visible in every state, beside the coverage figures (Rule 6).
 */

// Why a ticker has no range (backend `reasons`, same codes as the debate panel's refusals).
const REASON_TEXT = {
  delisted: 'it is delisted',
  insufficient_history: 'there is not enough price history',
  stale: 'its stored prices are out of date — refresh the ticker',
  near_gap: 'its price history has missing sessions',
  hard_quality_flag: 'a recent price failed a data-quality check',
}

function describeReasons(reasons) {
  const named = reasons.map((reason) => REASON_TEXT[reason] ?? reason.replaceAll('_', ' '))
  return `No range for this ticker: ${named.join('; ')}.`
}

// "about 2 in 3" for the 0.68 nominal level, else "about N%" with N to the nearest 5, so a
// retrain at another level cannot leave a wrong sentence behind.
function coverageWords(coverage) {
  if (Math.abs(coverage - 0.68) < 0.005) return 'about 2 in 3'
  return `about ${Math.round((coverage * 100) / 5) * 5}%`
}

// "N of the last M five-session moves", or null when the response cannot support one: a missing
// object, no windows, or no rate (the backend leaves `rate` null under 20 windows).
function hitRateText(hitRate) {
  if (!hitRate || !(hitRate.n > 0) || !Number.isFinite(hitRate.rate)) return null
  return `${Math.round(hitRate.rate * hitRate.n)} of the last ${hitRate.n} five-session moves`
}

function stateFor(ticker, query) {
  if (!ticker) return { kind: 'no-ticker' }
  if (query.isLoading) return { kind: 'loading', message: 'Loading range…' }
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : undefined
    if (status === 404) {
      return {
        kind: 'not-loaded',
        message: `${ticker} hasn't been loaded yet. Load it from the ticker panel to see its range.`,
      }
    }
    return { kind: 'failed', message: `Couldn't load the range for ${ticker} — please try again.` }
  }
  const range = query.data
  if (!range) return { kind: 'loading', message: 'Loading range…' }
  if (!Number.isFinite(range.range_5s_pct)) {
    const reasons = Array.isArray(range.reasons) ? range.reasons : []
    return {
      kind: 'unavailable',
      message: reasons.length > 0 ? describeReasons(reasons) : 'Range unavailable for this ticker.',
    }
  }
  return { kind: 'available', range }
}

function AvailableBody({ range }) {
  const hitRate = hitRateText(range.range_hit_rate)
  return (
    <div className="range-display__result" data-kind="available">
      <p className="range-display__percent">±{range.range_5s_pct.toFixed(1)}%</p>
      <p className="range-display__label">Typical 5-session move</p>
      <p className="range-display__line">As of {range.as_of}</p>
      <p className="range-display__line">Horizon: 5 trading sessions</p>
      {range.range_coverage != null && (
        <p className="range-display__line">
          Nominal coverage: {coverageWords(range.range_coverage)} — not a guaranteed interval.
        </p>
      )}
      <p className="range-display__line">
        <span className="range-display__line-label">Stayed inside the range: </span>
        <span className="range-display__hit-rate" data-measured={hitRate ? 'true' : 'false'}>
          {hitRate ?? 'Not enough history to measure'}
        </span>
      </p>
    </div>
  )
}

// Same lines as the populated card, so selecting a ticker for the first time adds none.
function NoTickerBody() {
  return (
    <div className="range-display__result" data-kind="no-ticker">
      <p className="range-display__percent range-display__percent--placeholder">N/A</p>
      <p className="range-display__label">Typical 5-session move</p>
      <p className="range-display__line">As of —</p>
      <p className="range-display__line">Horizon: 5 trading sessions</p>
      <p className="range-display__line">Nominal coverage: —</p>
      <p className="range-display__line">
        <span className="range-display__line-label">Stayed inside the range: </span>—
      </p>
    </div>
  )
}

export function RangeDisplay({ ticker }) {
  const rangeQuery = useTickerRange(ticker)
  const state = stateFor(ticker, rangeQuery)

  return (
    <section className="range-display" aria-label={ticker ? `Range for ${ticker}` : 'Range'}>
      <h2 className="range-display__title">5-session range</h2>
      {state.kind === 'available' && <AvailableBody range={state.range} />}
      {state.kind === 'no-ticker' && <NoTickerBody />}
      {state.kind !== 'available' && state.kind !== 'no-ticker' && (
        <div
          className="range-display__state"
          data-kind={state.kind}
          role={state.kind === 'failed' ? 'alert' : undefined}
        >
          {state.kind === 'loading' && <span className="range-display__spinner" aria-hidden="true" />}
          <p className="range-display__message">{state.message}</p>
        </div>
      )}
      <p className="range-display__disclaimer">{INLINE_DISCLAIMER}</p>
    </section>
  )
}
