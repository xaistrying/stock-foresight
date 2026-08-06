## Why

M1-M4 built the data pipeline, features, model, and prediction API, but
there is no UI — `frontend/` is empty. Traders can't see a chart, load a
ticker, or view a prediction without hitting the API directly. M5 delivers
the first user-facing surface: a dashboard with a chart panel and a
ticker panel, backed by two small new read endpoints that the existing
API doesn't yet provide.

## What Changes

- Add `GET /tickers`: returns the fixed 9-ticker training set (sourced
  from `TRAINING_TICKERS` in `backend/app/ml/training.py` — no duplicate
  list) with each ticker's `loaded` / `features_computed` /
  `last_loaded_at` status from the `tickers` table.
- Add `GET /tickers/{ticker}/history`: returns pure OHLCV for a fixed
  300-trading-session trailing window. No indicator overlay, no
  `near_gap` field — v1 scope is price data only.
- Scaffold `frontend/` from scratch: Vite + React (npm), React Query for
  data fetching.
- Build the dashboard: ticker panel (fixed list of 9, from `GET
  /tickers`), chart panel (candles from `/history`), prediction display
  (converts `predicted_log_return` to a percentage; distinct states for
  ok / near_gap / not-loaded / feature-computation-failed), and a
  reserved placeholder panel for the M6 AI insight panel.
- `POST /tickers/{ticker}/load` gains an explicit `status` field
  (`"ok"` / `"rate_limited"` / `"invalid_symbol"` / `"no_data"`) in its
  response. Previously, a caught `RateLimitError`, a malformed ticker
  symbol, and a well-formed-but-nonexistent ticker all returned
  indistinguishable, ambiguous results — worse, testing found both the
  malformed-symbol and well-formed-but-empty cases weren't caught at
  all; they crashed with an unhandled `ValueError` or
  `tenacity.RetryError` respectively. This change catches both (via a
  shared `_classify_load_error` helper matching vnstock's known
  validation/no-data messages, unwrapping `RetryError` via
  `e.last_attempt.exception()` where needed) and names all failure
  kinds explicitly in the response. `/load` otherwise stays open to any
  ticker string.
- `GET /tickers/{ticker}/prediction` is unchanged and consumed as-is.
  Only the *prediction display* is restricted to the fixed list.

**Domain rule interactions:**

- **Rule 1** (target = 5-session log return): unaffected. M5 only
  consumes `predicted_log_return` from the existing `/prediction`
  contract; no change to how the target is computed.
- **Rule 2** (never show raw log return in the UI): honored — the
  frontend converts `predicted_log_return` to a simple percentage before
  rendering. The backend contract is unchanged; the raw log return
  remains a legitimate API-layer value, conversion is a display-layer
  responsibility.
- **Rule 6** (never frame output as investment advice): honored, and
  actively reinforced by this change. Restricting the prediction display
  to the 9 tickers the model was actually trained/backtested on (per
  `docs/MODEL_CARD.md`) prevents the UI from rendering a confident-looking
  prediction for a ticker the model has no validated basis for — this is
  a deliberate mitigation, not just a UX simplification for M5's scope.
- **Rules 3, 4, 5** (Confidence, Advice threshold, Sentiment proxy): not
  touched. These are M6 scope. M5 only reserves layout space for them via
  a placeholder panel; no confidence score, advice text, or sentiment
  proxy is computed or displayed in M5.

## Capabilities

### New Capabilities

- `ticker-catalog`: Serves the fixed set of tickers the model supports,
  with each ticker's data-load status, so the frontend can populate a
  ticker panel without duplicating `TRAINING_TICKERS`.
- `ticker-history`: Serves a bounded trailing OHLCV window for a ticker,
  for chart rendering.
- `dashboard-ui`: The Vite/React dashboard itself — ticker panel, chart
  panel, prediction display, and the M6 placeholder panel — and how it
  consumes the ticker-catalog, ticker-history, ticker-data-ingestion, and
  ticker-prediction capabilities together.

### Modified Capabilities

- `ticker-data-ingestion`: `load_ticker` gains a `status` field
  (`"ok"` / `"rate_limited"` / `"invalid_symbol"` / `"no_data"`) on
  every response, plus exception handling for both malformed ticker
  symbols (`ValueError`) and well-formed-but-nonexistent tickers
  (`tenacity.RetryError`, unwrapped) — discovered while designing M5's
  ticker-panel error states (task 4.4/5.4 couldn't be written concretely
  without it). Both cases were previously unhandled crashes; both are
  now fixed and documented in `docs/KNOWN_ISSUES.md` as closed.

## Impact

- **Backend**: new `backend/app/api/tickers.py` route(s) for `GET
  /tickers` and `GET /tickers/{ticker}/history`; reads from the existing
  `tickers` and `ohlcv` tables plus `TRAINING_TICKERS` in
  `backend/app/ml/training.py`. `load_ticker` in
  `backend/app/services/ticker_ingestion.py` gains a `status` field in
  its return value. No schema changes.
- **Frontend**: net-new `frontend/` tree (Vite + React + React Query),
  currently empty.
- **Dependencies**: adds `@tanstack/react-query` (or current package
  name) and a charting library to `frontend/package.json` (charting
  library choice deferred to design.md).
- **Docs**: none of `docs/DATA_DICTIONARY.md`, `docs/MODEL_CARD.md`, or
  `docs/DISCLAIMER.md` need changes — no new columns, no model change, no
  Advice/Confidence/Sentiment UI yet.
