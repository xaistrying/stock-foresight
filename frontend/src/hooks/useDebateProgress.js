import { useQuery } from '@tanstack/react-query'
import { getDebateProgress } from '../api/tickers'

export const PROGRESS_POLL_MS = 2000

/**
 * The stage the server reports for `ticker`'s run, polled every 2 s while a run is pending.
 *
 * `startedAt` is when that run began (useDebateAnalysis's `startedAt`), or null when none is
 * pending: polling follows it, and it is part of the cache key so a new run never starts with
 * the previous run's stage. Best effort: a failed poll keeps the last value (React Query keeps
 * `data` through a failed refetch) and is not retried or reported.
 *
 * `data` is { ticker, running, stage: 'round1'|'round2'|'synthesis'|null, elapsed_ms }.
 */
export function useDebateProgress(ticker, startedAt) {
  return useQuery({
    queryKey: ['debate-progress', ticker, startedAt],
    queryFn: () => getDebateProgress(ticker),
    enabled: Boolean(ticker) && startedAt != null,
    refetchInterval: PROGRESS_POLL_MS,
    retry: false,
  })
}
