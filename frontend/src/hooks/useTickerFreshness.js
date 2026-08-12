import { useQuery } from '@tanstack/react-query'
import { fetchTickerHistory, fetchTickerPrediction } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * Freshness states for a selectable ticker (design.md Decision 10,
 * tasks.md 7.4): Fresh / Stale / Loading / Unknown. Staleness compares
 * the stored prediction's `as_of` against the latest trading session
 * actually available in the ticker's data (`/history`'s last row) — not
 * a fixed calendar-age threshold, so a holiday gap with genuinely no
 * newer session doesn't read as stale.
 */
export const FRESHNESS = {
  LOADING: 'loading',
  FRESH: 'fresh',
  STALE: 'stale',
  UNKNOWN: 'unknown',
}

/**
 * Derives a ticker's freshness from its prediction and history queries.
 * `enabled` lets callers defer fetching until the ticker is actually
 * loaded (a not-yet-loaded ticker has no freshness to compute yet).
 */
export function useTickerFreshness(ticker, { enabled = true } = {}) {
  const predictionQuery = useQuery({
    queryKey: queryKeys.prediction(ticker),
    queryFn: () => fetchTickerPrediction(ticker),
    enabled: enabled && Boolean(ticker),
    retry: false,
  })

  const historyQuery = useQuery({
    queryKey: queryKeys.history(ticker),
    queryFn: () => fetchTickerHistory(ticker),
    enabled: enabled && Boolean(ticker),
    retry: false,
  })

  if (!enabled || !ticker) {
    return { freshness: FRESHNESS.UNKNOWN, predictionQuery, historyQuery }
  }

  if (predictionQuery.isLoading || historyQuery.isLoading) {
    return { freshness: FRESHNESS.LOADING, predictionQuery, historyQuery }
  }

  if (predictionQuery.isError || historyQuery.isError) {
    return { freshness: FRESHNESS.UNKNOWN, predictionQuery, historyQuery }
  }

  const predictionAsOf = predictionQuery.data?.as_of
  const rows = historyQuery.data?.rows ?? []
  const latestSessionDate = rows.length > 0 ? rows[rows.length - 1].date : null

  if (!predictionAsOf || !latestSessionDate) {
    return { freshness: FRESHNESS.UNKNOWN, predictionQuery, historyQuery }
  }

  const freshness = predictionAsOf >= latestSessionDate ? FRESHNESS.FRESH : FRESHNESS.STALE
  return { freshness, predictionQuery, historyQuery }
}
