import { useQuery } from '@tanstack/react-query'
import { fetchTickerPrediction } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers/{ticker}/prediction — for the currently selected ticker
 * (tasks.md 8.3/9.1). 404 (not-loaded) and 5xx (feature-computation
 * failure) surface via ApiError on `query.error`; `query.error.status`
 * carries the HTTP status so callers can distinguish the two (tasks.md
 * 8.4/9.3) without re-parsing the message.
 */
export function useTickerPrediction(ticker) {
  return useQuery({
    queryKey: queryKeys.prediction(ticker),
    queryFn: () => fetchTickerPrediction(ticker),
    enabled: Boolean(ticker),
    retry: false,
  })
}
