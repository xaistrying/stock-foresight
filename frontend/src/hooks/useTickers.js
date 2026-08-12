import { useQuery } from '@tanstack/react-query'
import { fetchTickers } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers — the fixed 9 TRAINING_TICKERS with load status
 * (tasks.md 7.1). Searched-in tickers are not part of this response;
 * see useSearchedTickers for how they're tracked client-side.
 */
export function useTickers() {
  return useQuery({
    queryKey: queryKeys.tickers,
    queryFn: fetchTickers,
  })
}
