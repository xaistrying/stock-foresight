// Typed client functions for every ticker-related endpoint the dashboard
// consumes (tasks.md 6.4). Each function's return shape mirrors its
// backend route exactly — see backend/app/api/{tickers,predictions,
// insight}.py — so hooks/components can rely on the documented fields
// without re-deriving them.
import { get, post } from './client'

/**
 * GET /tickers
 * @returns {Promise<{tickers: Array<{ticker: string, loaded: boolean, features_computed: boolean|null, last_loaded_at: string|null}>}>}
 */
export function fetchTickers() {
  return get('/tickers')
}

/**
 * GET /tickers/{ticker}/history
 * 200: { ticker, rows: [{ date, open, high, low, close, volume }, ...] }
 * 404: ticker has never been loaded (thrown as ApiError with status 404)
 * @returns {Promise<{ticker: string, rows: Array<{date: string, open: number, high: number, low: number, close: number, volume: number}>}>}
 */
export function fetchTickerHistory(ticker) {
  return get(`/tickers/${encodeURIComponent(ticker)}/history`)
}

/**
 * GET /tickers/{ticker}/prediction
 * status "ok": { ticker, as_of, status, predicted_log_return }
 * status "near_gap": { ticker, as_of, status } (no predicted_log_return)
 * 404: never loaded; 503: feature computation failed — both thrown as ApiError.
 * @returns {Promise<{ticker: string, as_of: string, status: 'ok'|'near_gap', predicted_log_return?: number}>}
 */
export function fetchTickerPrediction(ticker) {
  return get(`/tickers/${encodeURIComponent(ticker)}/prediction`)
}

/**
 * GET /tickers/{ticker}/insight
 * status "ok" | "near_gap": { ticker, as_of, status, confidence_score,
 *   confidence_basis, sentiment_proxy, sentiment_inputs, advice_text, note }
 * 404: never loaded; 503: feature computation failed — thrown as ApiError.
 * @returns {Promise<{
 *   ticker: string, as_of: string, status: 'ok'|'near_gap',
 *   confidence_score: number|null, confidence_basis: string,
 *   sentiment_proxy: 'bullish'|'bearish'|'neutral', sentiment_inputs: string[],
 *   advice_text: string|null, note: string|null,
 * }>}
 */
export function fetchTickerInsight(ticker) {
  return get(`/tickers/${encodeURIComponent(ticker)}/insight`)
}

/**
 * POST /tickers/{ticker}/load
 * Response `status`: "ok" | "rate_limited" | "invalid_symbol" | "no_data".
 * Resolves (does not throw) for all four — this endpoint reports outcomes
 * via the body's `status` field rather than HTTP status codes (design.md
 * Decision 4/7), so callers branch on `status`, not on catch vs. then.
 * @returns {Promise<{ticker: string, status: 'ok'|'rate_limited'|'invalid_symbol'|'no_data', rows_loaded?: number, available_since?: string|null, possibly_truncated_by_tier?: boolean|null}>}
 */
export function loadTicker(ticker) {
  return post(`/tickers/${encodeURIComponent(ticker)}/load`)
}

/**
 * POST /tickers/{ticker}/backtest
 * 200: { ticker, rows_backtested, folds }
 * 409: below SINGLE_TICKER_BACKTEST_MIN_ROWS — thrown as ApiError (design.md
 * Decision 12); callers should show the gated explanation, not a generic error.
 * @returns {Promise<{ticker: string, rows_backtested: number, folds: number[]}>}
 */
export function backtestTicker(ticker) {
  return post(`/tickers/${encodeURIComponent(ticker)}/backtest`)
}
