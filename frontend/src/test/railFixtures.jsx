import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Shared fixtures for the Rail, the topbar search and the app-level tests: a catalog entry in the
// shape GET /tickers serves (eligibility included), and a render helper with a fresh QueryClient
// (never the app's singleton, so cache and retry state do not leak between tests).

export const DAY_MS = 24 * 60 * 60 * 1000
export const daysAgo = (days) => new Date(Date.now() - days * DAY_MS).toISOString()

export const ELIGIBLE = { eligible: true, reasons: [], as_of: '2026-10-06', age_sessions: 0 }
export const ineligible = (reasons, ageSessions = 21) => ({
  eligible: false,
  reasons,
  as_of: '2026-09-07',
  age_sessions: ageSessions,
})

/** A `GET /tickers` entry. */
export function catalogEntry(ticker, overrides = {}) {
  return {
    ticker,
    in_training_set: false,
    exchange: 'HOSE',
    industry_code: null,
    listing_status: 'listed',
    loaded: true,
    features_computed: true,
    last_loaded_at: daysAgo(2),
    eligibility: ELIGIBLE,
    ...overrides,
  }
}

export function newQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
}

export function renderWithQuery(ui, queryClient = newQueryClient()) {
  return { queryClient, ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>) }
}
