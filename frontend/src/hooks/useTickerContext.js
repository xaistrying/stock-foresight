import { useTickers } from './useTickers'
import { useTickerHistory } from './useTickerHistory'
import { useTickerRange } from './useTickerRange'
import { resolveEligibility } from '../lib/verdictState'

/**
 * What the Stage header and the Verdict panel need to know about the selected ticker before any
 * debate has run, from three shared cache entries (the catalog, `/history`, `/range`; the first is
 * the page's only load request, the other two are fetched for the selected ticker alone):
 *
 * - `ageSessions`, `reasons`, `eligible`: the catalog entry's `eligibility`, which the server computed
 *   with `assess_eligibility`. A ticker the catalog does not list (searched in) has no age: the
 *   dashboard never works one out, because its browser cannot know market holidays or other tickers'
 *   stored sessions, and two answers to "Stale" on one screen is worse than none.
 * - `stale` is whether the server's `reasons` contain `stale`, never a comparison of an age with a
 *   number of this dashboard's own.
 * - Without a catalog `eligibility`, the reasons and eligibility come from `/range`'s `status` and
 *   `reasons` (which carry the same reasons, minus `indicators_missing`).
 * - `asOf` is `/range`'s `as_of`, else the last history row's date; `lastClose` the last history row's.
 *
 * @param {string|null} ticker
 * @returns {{asOf: string|null, ageSessions: number|null, stale: boolean, reasons: string[],
 *   eligible: boolean|null, lastClose: number|null}}
 */
export function useTickerContext(ticker) {
  const catalog = useTickers()
  const history = useTickerHistory(ticker)
  const range = useTickerRange(ticker)

  const entry = ticker ? catalog.data?.tickers.find((candidate) => candidate.ticker === ticker) : undefined
  const eligibility = entry?.eligibility ?? null
  const served = ticker ? range.data : undefined
  const rows = ticker ? (history.data?.rows ?? []) : []
  const lastRow = rows[rows.length - 1]

  const { eligible, reasons, ageSessions } = resolveEligibility(eligibility, served)

  return {
    asOf: served?.as_of ?? lastRow?.date ?? null,
    ageSessions,
    stale: reasons.includes('stale'),
    reasons,
    eligible,
    lastClose: lastRow?.close ?? null,
  }
}
