import { skipToken, useMutation, useMutationState, useQuery, useQueryClient } from '@tanstack/react-query'
import { runDebateAnalysis } from '../api/tickers'

// Both keys are parameterized by ticker, so every ticker has its own run and its own kept result.
const runKey = (ticker) => ['debate', ticker]
const resultKey = (ticker) => ['debate-result', ticker]

/**
 * `POST /tickers/{ticker}/debate` as an on-demand run, with the last result kept per ticker.
 *
 * The analysis is always user-initiated (clicking "Analyse") — never auto-fetched on ticker
 * selection (design.md Decision 9). Everything the panel shows comes from the React Query
 * caches, not from this component instance, so it survives the panel being unmounted by a
 * ticker switch (`App` keys the panel by ticker):
 *
 * - a run is a mutation under ['debate', ticker]; switching ticker does not abort it, and
 *   `isPending` / `startedAt` / `error` are read from the mutation cache by key;
 * - a finished run's result is stored under ['debate-result', ticker] with the time it
 *   finished, in memory only (never persisted: an old verdict must not look fresh after a
 *   reload) and never garbage collected until the page reloads or that ticker is analysed again;
 * - a failed run does not remove the kept result: `error` is the latest run's error, `result`
 *   stays the last success. (Unlike the result, a failed run's error is forgotten five minutes
 *   after the panel is left: React Query collects the finished mutation. That is intended.)
 *
 * Returns { analyse, isPending, startedAt (ms, while pending), result, completedAt (ms), error }.
 */
export function useDebateAnalysis(ticker) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationKey: runKey(ticker),
    mutationFn: () => runDebateAnalysis(ticker),
    // The result may land after the user switched ticker and this component is gone: a
    // mutation-level callback still runs, and the entry below already exists (see `stored`).
    onSuccess: (result) => {
      queryClient.setQueryData(resultKey(ticker), { result, completedAt: Date.now() })
    },
  })

  // skipToken: this query only ever holds what `onSuccess` stored; it never fetches. Mounting it
  // creates the entry with gcTime Infinity (it stays Infinity after unmount), so a kept result is
  // never collected.
  const stored = useQuery({
    queryKey: resultKey(ticker),
    queryFn: skipToken,
    gcTime: Infinity,
    staleTime: Infinity,
  })

  const runs = useMutationState({
    filters: { mutationKey: runKey(ticker) },
    select: (run) => ({
      status: run.state.status,
      error: run.state.error,
      submittedAt: run.state.submittedAt,
    }),
  })
  const latest = runs.at(-1)
  const isPending = latest?.status === 'pending'

  return {
    // A second click while a run is going starts nothing: the first run is the one to wait for.
    analyse: () => {
      if (!isPending) mutation.mutate()
    },
    isPending,
    startedAt: isPending ? latest.submittedAt : null,
    result: stored.data?.result ?? null,
    completedAt: stored.data?.completedAt ?? null,
    error: latest?.status === 'error' ? latest.error : null,
  }
}
