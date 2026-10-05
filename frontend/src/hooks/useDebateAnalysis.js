import { useMutation } from '@tanstack/react-query'
import { runDebateAnalysis } from '../api/tickers'

/**
 * Wraps `POST /tickers/{ticker}/debate` as an on-demand React Query mutation.
 *
 * The debate analysis is always user-initiated (clicking "Analyse") — never
 * auto-fetched on ticker selection. This matches the on-demand design in
 * design.md Decision 9.
 *
 * Returns the standard mutation object: { mutate, isPending, isSuccess,
 * isError, data, error, reset }.
 */
export function useDebateAnalysis(ticker) {
  return useMutation({
    mutationFn: () => runDebateAnalysis(ticker),
  })
}
