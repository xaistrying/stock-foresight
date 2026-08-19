import { useQuery } from '@tanstack/react-query'
import { fetchTickerInsight } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers/{ticker}/insight — Confidence, Sentiment, and Advice for the
 * currently selected ticker (tasks.md 10.1). 404 (not-loaded) and 5xx
 * (feature-computation failure) surface via ApiError on `query.error`, same
 * convention as `useTickerPrediction`.
 *
 * `options.enabled` (redesign-dashboard-visual-look adjacent fix) lets a
 * caller other than `AIInsightPanel` warm this exact query's cache ahead
 * of selection — see `TickerChip`, which does this for every Watchlist
 * ticker the same way `useTickerFreshness` already warms `prediction`/
 * `history`. Defaults to `true` (today's `AIInsightPanel` behavior,
 * gated only on a ticker being selected) so existing callers are
 * unaffected.
 */
export function useTickerInsight(ticker, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.insight(ticker),
    queryFn: () => fetchTickerInsight(ticker),
    enabled: enabled && Boolean(ticker),
    retry: false,
  })
}
