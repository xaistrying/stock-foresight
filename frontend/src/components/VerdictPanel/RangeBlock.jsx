import { useTickerRange } from '../../hooks/useTickerRange'
import { ApiError } from '../../api/client'
import { INLINE_DISCLAIMER } from '../../lib/disclaimer'
import { formatBandPct } from '../../lib/formatBand'
import './range-block.css'

// Why a ticker has no range (backend `reasons`, same codes as the Verdict panel's refusals).
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

// "about 2 in 3" for the 0.68 nominal level, else "about N%" with N to the nearest 5, so a retrain at
// another level cannot leave a wrong sentence behind.
function coverageWords(coverage) {
  if (Math.abs(coverage - 0.68) < 0.005) return 'about 2 in 3'
  return `about ${Math.round((coverage * 100) / 5) * 5}%`
}

// "N of the last M five-session moves stayed inside it", or null when the response cannot support one:
// a missing object, no windows, or no rate (the backend leaves `rate` null under 20 windows).
function hitRateSentence(hitRate) {
  if (!hitRate || !(hitRate.n > 0) || !Number.isFinite(hitRate.rate)) return null
  return `${Math.round(hitRate.rate * hitRate.n)} of the last ${hitRate.n} five-session moves stayed inside it`
}

function stateFor(ticker, query) {
  if (!ticker) return { kind: 'no-ticker' }
  if (query.isLoading) return { kind: 'loading', message: 'Loading range…' }
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : undefined
    if (status === 404) {
      return {
        kind: 'not-loaded',
        message: `${ticker} hasn't been loaded yet. Load it with the search above to see its range.`,
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

// The band is calibrated when the response carries a coverage. Without one, its multiplier was not
// fitted for this ticker, so its hit-rate is not a check of a calibrated band: none is shown.
function AvailableBody({ range }) {
  const calibrated = range.range_coverage != null
  const hitRate = hitRateSentence(range.range_hit_rate)
  return (
    <div className="range-block__body" data-kind="available">
      <p className="range-block__figure t-kpi">{formatBandPct(range.range_5s_pct)}</p>
      {calibrated ? (
        <>
          <div className="range-block__slot range-block__check">
            <p className="range-block__check-label t-label">Range hit-rate</p>
            <p className="t-small">{hitRate ?? 'Not enough history to check the range'}</p>
          </div>
          <p className="range-block__slot t-small">
            Nominal coverage: {coverageWords(range.range_coverage)} — not a guaranteed interval.
          </p>
        </>
      ) : (
        <p className="range-block__slot t-small">Not calibrated for this ticker</p>
      )}
    </div>
  )
}

// The same slots as a populated block, so selecting a ticker for the first time adds no lines.
function NoTickerBody() {
  return (
    <div className="range-block__body" data-kind="no-ticker">
      <p className="range-block__figure range-block__figure--placeholder t-kpi">N/A</p>
      <p className="range-block__slot t-small">—</p>
      <p className="range-block__slot t-small">—</p>
    </div>
  )
}

/**
 * The range block: the typical 5-session move for the selected ticker, from `GET /tickers/{t}/range`.
 * It states a size, never a direction: an unsigned `±4.12%` (the same string as the chart's band
 * label), no up or down colour, and `sigma_daily_pct` is never rendered. Under it, the range check
 * ("Range hit-rate": how many of the last M five-session moves stayed inside it, measured from price
 * history, Rule 4) and the nominal coverage, stated as not a guaranteed interval.
 *
 * States: no ticker (placeholders in the same shape), loading, available, unavailable (200 with no
 * `range_5s_pct`), not loaded (404) and failed (5xx or network). "Available" means `range_5s_pct` is a
 * number; `status` and `reasons` are display text only.
 *
 * It sits at the top of the Verdict panel (above the chart on phones). `disclaimer` adds the inline
 * disclaimer for the case where it stands outside the panel that carries it.
 */
export function RangeBlock({ ticker, disclaimer = false }) {
  const rangeQuery = useTickerRange(ticker)
  const state = stateFor(ticker, rangeQuery)

  return (
    <section className="range-block" aria-label={ticker ? `Range for ${ticker}` : 'Range'}>
      <p className="range-block__label t-label">Typical 5-session move</p>
      {state.kind === 'available' && <AvailableBody range={state.range} />}
      {state.kind === 'no-ticker' && <NoTickerBody />}
      {state.kind !== 'available' && state.kind !== 'no-ticker' && (
        <div
          className="range-block__state t-small"
          data-kind={state.kind}
          role={state.kind === 'failed' ? 'alert' : undefined}
        >
          {state.kind === 'loading' && <span className="range-block__spinner" aria-hidden="true" />}
          <p className="range-block__message">{state.message}</p>
        </div>
      )}
      {disclaimer ? <p className="range-block__disclaimer t-small">{INLINE_DISCLAIMER}</p> : null}
    </section>
  )
}
