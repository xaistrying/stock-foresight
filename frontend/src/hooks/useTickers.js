import { useQuery } from '@tanstack/react-query'
import { fetchTickers } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

/**
 * GET /tickers — the universe-derived catalog with each ticker's load status. It is the
 * dashboard's only request on page load. Searched-in tickers are not part of this response
 * until they are loaded; see useSearchedTickers for how they're tracked client-side.
 */
export function useTickers() {
  return useQuery({
    queryKey: queryKeys.tickers,
    queryFn: fetchTickers,
  })
}
