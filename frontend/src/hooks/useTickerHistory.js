import { useQuery } from '@tanstack/react-query'
import { fetchTickerHistory } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers/{ticker}/history — the fixed 300-session OHLCV window for
 * the currently selected ticker (tasks.md 8.1). `enabled: false` when no
 * ticker is selected yet.
 */
export function useTickerHistory(ticker) {
  return useQuery({
    queryKey: queryKeys.history(ticker),
    queryFn: () => fetchTickerHistory(ticker),
    enabled: Boolean(ticker),
    retry: false,
  })
}
