import { useQuery } from '@tanstack/react-query'
import { fetchTickerInsight } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers/{ticker}/insight — Confidence, Sentiment, and Advice for the
 * currently selected ticker (tasks.md 10.1). 404 (not-loaded) and 5xx
 * (feature-computation failure) surface via ApiError on `query.error`, same
 * convention as `useTickerPrediction`.
 */
export function useTickerInsight(ticker) {
  return useQuery({
    queryKey: queryKeys.insight(ticker),
    queryFn: () => fetchTickerInsight(ticker),
    enabled: Boolean(ticker),
    retry: false,
  })
}
