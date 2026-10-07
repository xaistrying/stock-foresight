import { QueryClient } from '@tanstack/react-query'

// Single shared QueryClient for the app. Defaults kept conservative — the
// dashboard's data (prices, range) is only as fresh as the last `/load`, so
// React Query must not silently refetch on every window focus and hide how
// old the stored data is (each chip says "Loaded Nd ago").
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Centralized query keys so invalidation (design.md Decision 5's
// write-then-invalidate flow: load -> invalidate catalog/history/range)
// stays consistent across hooks instead of ad-hoc key arrays per call site.
export const queryKeys = {
  tickers: ['tickers'],
  history: (ticker) => ['ticker-history', ticker],
  range: (ticker) => ['ticker-range', ticker],
}
