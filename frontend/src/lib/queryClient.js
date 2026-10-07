import { QueryClient } from '@tanstack/react-query'

// The dashboard's data (the catalog, prices, range) is only as fresh as the last `/load`, so React
// Query must not silently refetch it: not on window focus, and not when a component that reads it
// mounts again (a layout change moves the range block and the Rail in and out of the tree). It is
// refetched when a load invalidates it, which is what keeps the "Loaded Nd ago" text honest.
export const queryDefaults = {
  refetchOnWindowFocus: false,
  staleTime: Infinity,
}

// Single shared QueryClient for the app.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, ...queryDefaults },
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
