import { useMutation, useQueryClient } from '@tanstack/react-query'
import { backtestTicker } from '../api/tickers'
import { queryKeys } from '../lib/queryClient'
import { ApiError } from '../api/client'

/**
 * Wraps `POST /tickers/{ticker}/backtest` as a React Query mutation for the
 * "Backtest this ticker" action (tasks.md 10.3, design.md Decision 12).
 *
 * There is no separate read-only gate-check endpoint — `SINGLE_TICKER_
 * BACKTEST_MIN_ROWS` is only enforced inside `POST /backtest` itself
 * (backend/app/api/tickers.py), which 409s below the threshold rather than
 * attempting a degenerate backtest. This hook exposes that 409 as
 * `isBelowThreshold` so the action can render "needs more history" text
 * distinctly from a genuine failure, rather than treating both the same.
 *
 * On success, invalidates this ticker's `/insight` query so Confidence
 * refetches and displays the real hit-rate (dashboard-ui spec: "Completed
 * backtest transitions Confidence to a real value").
 */
export function useBacktestTicker(ticker) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => backtestTicker(ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.insight(ticker) })
    },
  })

  const isBelowThreshold =
    mutation.isError && mutation.error instanceof ApiError && mutation.error.status === 409

  return { ...mutation, isBelowThreshold }
}
