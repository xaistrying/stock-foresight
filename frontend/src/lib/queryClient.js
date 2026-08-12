import { QueryClient } from '@tanstack/react-query'

// Single shared QueryClient for the app (tasks.md 6.2). Defaults kept
// conservative — the dashboard's data (prices, predictions, insight) is
// only as fresh as the last `/load`, so we don't want React Query silently
// refetching on every window focus and masking staleness that the ticker
// panel's own Fresh/Stale state (design.md Decision 10) is responsible for
// surfacing explicitly.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Centralized query keys so invalidation (design.md Decision 5's
// write-then-invalidate flow: load -> invalidate prediction/history/insight)
// stays consistent across hooks instead of ad-hoc key arrays per call site.
export const queryKeys = {
  tickers: ['tickers'],
  history: (ticker) => ['ticker-history', ticker],
  prediction: (ticker) => ['ticker-prediction', ticker],
  insight: (ticker) => ['ticker-insight', ticker],
}
