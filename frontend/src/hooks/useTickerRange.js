import { useQuery } from '@tanstack/react-query'
import { fetchTickerRange } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers/{ticker}/range — the calibrated 5-session band for the currently selected
 * ticker, read by the range card and the chart band through one shared cache entry.
 * `enabled: false` when no ticker is selected, so nothing is fetched for an unselected
 * ticker. 404 (not loaded) and 5xx surface via ApiError on `query.error`.
 */
export function useTickerRange(ticker) {
  return useQuery({
    queryKey: queryKeys.range(ticker),
    queryFn: () => fetchTickerRange(ticker),
    enabled: Boolean(ticker),
    retry: false,
  })
}
