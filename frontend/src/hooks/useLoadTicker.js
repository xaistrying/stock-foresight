import { useMutation, useMutationState, useQueryClient } from '@tanstack/react-query'
import { loadTicker } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'

// Mutation key namespace, parameterized by ticker, so multiple chips can
// each be loading concurrently and every caller can ask "is *my* ticker's
// load in flight" without one shared isPending flag conflating them
// (React Query v5's useMutation().isPending is per-hook-instance, not
// per-argument — a single shared instance couldn't distinguish "TCB is
// loading" from "VIB is loading" if both are clicked in quick succession).
const loadMutationKey = (ticker) => ['load-ticker', ticker]

// One message per `/load` status value (design.md Decision 4/7, tasks.md
// 6.5/7.6) — each reachable from both a chip click and search, so no
// caller should special-case which entry point triggered the load.
// Kept distinct on purpose: collapsing any of these into a shared/generic
// message is exactly what tasks.md 7.6 and 12.4 check for.
export const LOAD_STATUS_MESSAGES = {
  ok: null,
  rate_limited: 'Rate-limited by the data provider — try again in a moment.',
  invalid_symbol: (ticker) => `"${ticker}" isn't a recognized ticker symbol.`,
  no_data: (ticker) => `No data is available for "${ticker}" — retrying is unlikely to help.`,
}

export function describeLoadStatus(status, ticker) {
  const entry = LOAD_STATUS_MESSAGES[status]
  return typeof entry === 'function' ? entry(ticker) : entry
}

/**
 * Wraps `POST /tickers/{ticker}/load` as a React Query mutation. On a
 * successful load (`status: "ok"`), invalidates this ticker's catalog
 * entry, history, prediction, and insight so the auto-predict-on-load flow
 * (design.md Decision 11, tasks.md 7.5) has fresh data to refetch — no
 * separate user action needed. `ticker` is fixed per hook call so its
 * mutationKey can be ticker-scoped (see loadMutationKey above).
 */
export function useLoadTicker(ticker) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationKey: loadMutationKey(ticker),
    mutationFn: () => loadTicker(ticker),
    onSuccess: (result) => {
      if (result.status !== 'ok') return
      queryClient.invalidateQueries({ queryKey: queryKeys.tickers })
      queryClient.invalidateQueries({ queryKey: queryKeys.history(ticker) })
      queryClient.invalidateQueries({ queryKey: queryKeys.prediction(ticker) })
      queryClient.invalidateQueries({ queryKey: queryKeys.insight(ticker) })
    },
  })
}

/**
 * True while `ticker`'s own load mutation is in flight, regardless of
 * which component instance triggered it (chip vs. search can observe the
 * same in-flight state for the same ticker).
 */
export function useIsTickerLoading(ticker) {
  const states = useMutationState({
    filters: { mutationKey: loadMutationKey(ticker), status: 'pending' },
  })
  return states.length > 0
}
