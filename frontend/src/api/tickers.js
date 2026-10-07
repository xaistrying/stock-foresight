// Typed client functions for every ticker-related endpoint the dashboard
// consumes. Each function's return shape mirrors its backend route
// exactly — see backend/app/api/{tickers,range,debate}.py — so
// hooks/components can rely on the documented fields without re-deriving
// them.
import { get, post } from './client'

/**
 * GET /tickers
 *
 * Universe-derived since hose-universe-ingestion task 8.1: this returns
 * every ingested symbol passing the universe's default filters (hundreds),
 * not the nine training tickers. `in_training_set` is a legacy marker for
 * the nine tickers the retired direction model was trained on; nothing in
 * the dashboard reads it.
 *
 * Universe fields are null (never omitted) for a symbol the universe has no
 * value for; `features_computed` and `last_loaded_at` are null when the
 * symbol has never been loaded.
 * @returns {Promise<{tickers: Array<{ticker: string, in_training_set: boolean, exchange: string|null, industry_code: string|null, listing_status: string|null, loaded: boolean, features_computed: boolean|null, last_loaded_at: string|null}>}>}
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
 * GET /tickers/{ticker}/range
 * 200: { ticker, as_of, status, reasons, sigma_daily_pct, range_5s_pct, range_k,
 *   range_coverage, range_hit_rate }. `range_5s_pct` is null whenever `status` refuses a
 *   range ('ineligible', 'model_unavailable', 'range_out_of_bounds'); `range_hit_rate` is
 *   `{ rate, n }` with `rate` null under 20 windows.
 * 404: never loaded (thrown as ApiError with status 404).
 * @returns {Promise<{
 *   ticker: string, as_of: string, status: string, reasons: string[],
 *   sigma_daily_pct: number|null, range_5s_pct: number|null, range_k: number|null,
 *   range_coverage: number|null, range_hit_rate: {rate: number|null, n: number}|null,
 * }>}
 */
export function fetchTickerRange(ticker) {
  return get(`/tickers/${encodeURIComponent(ticker)}/range`)
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

// The server stops a run after 180 s (DEBATE_RUN_TIMEOUT_SECONDS) and answers 504; the client
// waits 20 s longer for that answer to arrive before it gives up.
export const DEBATE_CLIENT_TIMEOUT_MS = 200_000

// AbortSignal.timeout where it exists (every current browser), a timer elsewhere. `clear` stops
// that timer once the request is over; the native one needs no cleanup.
function timeoutSignal(ms) {
  if (typeof AbortSignal.timeout === 'function') return { signal: AbortSignal.timeout(ms), clear: () => {} }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('The operation timed out.', 'TimeoutError')), ms)
  return { signal: controller.signal, clear: () => clearTimeout(timer) }
}

/**
 * What the backend serialises for one run (backend/app/api/debate.py `_serialise_result`).
 * @typedef {object} DebateResult
 * @property {string} ticker
 * @property {string|null} as_of
 * @property {'STRONG_BUY_SIGNAL'|'BUY_SIGNAL'|'OBSERVE'|'CAUTION_SIGNAL'|'STRONG_CAUTION_SIGNAL'|'SPLIT'|'INSUFFICIENT_DATA'} verdict
 * @property {'unanimous'|'majority'|'split'|'none'} agreement_level
 * @property {Record<string, object>} round1 Agent positions keyed by agent id.
 * @property {Record<string, object>} round2
 * @property {{verdict: string, agreement_level: string, key_tension: string|null, reasoning: string}} synthesis
 * @property {number} duration_ms
 * @property {number|null} [range_5s_pct]
 * @property {number|null} [sigma_daily_pct]
 * @property {number|null} [range_coverage]
 * @property {string|null} [data_as_of]
 * @property {number|null} [data_age_sessions]
 * @property {string[]} [agents_degraded]
 * @property {{eligible: boolean, reasons: string[]}} [eligibility]
 * @property {boolean} report_saved
 * @property {string|null} report_file
 */

/**
 * POST /tickers/{ticker}/debate
 * Runs the multi-agent debate analysis for a loaded ticker.
 * Returns a DebateResult with verdict, agreement_level, round1, round2, synthesis, and
 * `report_saved` / `report_file` (whether the server wrote the exported report).
 *
 * Gives up after `timeoutMs` (default DEBATE_CLIENT_TIMEOUT_MS) with an ApiError whose
 * `timedOut` is true; the server may still be working, and asking again joins its run.
 * Other failures: 404 never loaded; 429 `debate_busy`; 503 `debate_not_configured`;
 * 504 `debate_timeout` — each an ApiError with `status` and `body.code`.
 * @returns {Promise<DebateResult>}
 */
export function runDebateAnalysis(ticker, { timeoutMs = DEBATE_CLIENT_TIMEOUT_MS, signal } = {}) {
  const limit = signal ? { signal, clear: () => {} } : timeoutSignal(timeoutMs)
  return post(`/tickers/${encodeURIComponent(ticker)}/debate`, undefined, { signal: limit.signal }).finally(limit.clear)
}

/**
 * GET /tickers/{ticker}/debate/progress
 * { ticker, running, stage: 'round1'|'round2'|'synthesis'|null, elapsed_ms: number|null }
 * Never starts a run and never 404s.
 */
export function getDebateProgress(ticker) {
  return get(`/tickers/${encodeURIComponent(ticker)}/debate/progress`)
}
