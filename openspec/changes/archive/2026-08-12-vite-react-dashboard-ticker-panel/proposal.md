## Why

M1-M4 built the data pipeline, features, model, and prediction API, but
there is no UI — `frontend/` is empty. Traders can't see a chart, load a
ticker, or view a prediction without hitting the API directly. M5
delivers the first user-facing surface: a dashboard with a chart panel,
a ticker panel, and — **absorbed from the original M6 scope, not
deferred as a placeholder** — the AI insight panel (Confidence,
Sentiment, Advice, disclaimer). This scope decision came out of an
`/opsx:explore` session (2026-08-11, see
`docs/M5_DASHBOARD_EXPLORE_NOTES.md`) prompted by a UI reference
screenshot; several of the screenshot's affordances (a free-adjustable
horizon slider, a disclaimer visibility toggle, a smooth forecast curve)
were deliberately rejected as domain-rule conflicts rather than carried
over, and are recorded there with rationale.

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
- Build the dashboard: ticker panel (9 fixed chips from `GET /tickers`,
  always shown, plus a search box that resolves and loads any real
  ticker — see ticker panel below), chart panel (candles from
  `/history`, plus the single predicted point described below),
  prediction display (converts `predicted_log_return` to a percentage;
  distinct states for ok / near_gap / not-loaded /
  feature-computation-failed), and the **AI insight panel** — Confidence,
  Sentiment, Advice, and an unconditional disclaimer.
- **Ticker panel and search**: the 9 chips are always shown. The search
  box resolves any real ticker (not limited to the 9); if it isn't yet
  in the DB, search triggers the same `POST /tickers/{ticker}/load` flow
  an unloaded chip's click would, and the ticker joins the selectable
  list once loaded. Each ticker (chip or searched-in) shows a
  **Loading** / **Fresh** / **Stale** state — Stale means a newer
  trading session's data is available than the one the stored
  prediction's `as_of` used.
- **Auto-predict on load**: loading a ticker (chip or search) immediately
  triggers its prediction too, with no separate user action. Confirmed
  safe against model-drift concerns: the served model
  (`app.state.model`) is a frozen, read-only artifact loaded once at
  FastAPI startup — a prediction call is a forward pass only, never a
  retrain, so this cannot destabilize the model regardless of how many
  tickers get searched in.
- **AI insight panel — Confidence** differs by ticker origin. For the 9
  `TRAINING_TICKERS`, Confidence shows `compute_rolling_hit_rate`'s real
  value (existing M3 code, not previously wired into any UI). For a
  searched-in ticker, `compute_rolling_hit_rate` returns `None` — there
  is no live/incremental backtest mechanism, only the offline M3
  training job, and that job only ever covers the 9 — so Confidence
  shows an explicit `N/A` state instead of a fabricated number, with a
  **"Backtest this ticker"** button once the ticker has enough
  clean+labeled feature rows to form a walk-forward fold. Clicking it
  runs a scoped-down, single-ticker walk-forward backtest (new
  `single-ticker-backtest` capability, below); the rest of the panel
  stays interactive while it runs.
- **AI insight panel — Sentiment**: labeled "Technical Signal" (not
  "Market Sentiment") with the computing indicators (RSI, MACD, Ichimoku
  position) named inline, not hidden in a tooltip — reinforcing Rule 5.
  Computed the same way for any ticker, trained or searched-in, since it
  reads live from that ticker's own price history with no training-set
  dependency.
- **AI insight panel — Advice**: volatility-relative per Rule 3, worded
  directionally (`HOLD` / `Signal: up` / `Signal: down`) rather than
  `BUY`/`SELL` — those are literal transaction verbs and read as
  instructions to act, which Rule 6 requires this panel to avoid.
- **AI insight panel — Disclaimer**: always visible alongside
  Confidence/Sentiment/Advice, with no visibility toggle. This is the
  first change to actually render Advice/Confidence/Sentiment in the UI,
  so `docs/DISCLAIMER.md` is created by this change (see Impact).
- **Chart panel**: renders OHLCV candles, plus the single predicted point
  at t+5 (from `predicted_log_return`, converted per Rule 2) connected to
  today's close by one straight dashed line. No interpolated/fabricated
  intermediate points, no indicator overlay (Ichimoku/RSI/MACD/etc.) —
  see Domain rule interactions below for why this narrows, rather than
  violates, the "no predicted-vs-actual series" instinct.
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
  ticker string — which the ticker panel's search now actually exercises,
  rather than leaving unused.
- `GET /tickers/{ticker}/prediction` is unchanged and consumed as-is.
  The *prediction display* is no longer restricted to the fixed list —
  see Domain rule interactions below for how Rule 6 is honored without
  that restriction.

## Post-ship UI refinements (2026-08-12)

After initial implementation, real usage against the live dashboard
surfaced several UI issues, each fixed in a follow-up pass (see design.md
Decisions 15-19 for full rationale):

- **T+5 line placement**: the chart's predicted point was placed using a
  flat `as_of + 7 calendar days` approximation, which lightweight-charts'
  time scale rendered immediately adjacent to the last candle (reading as
  "tomorrow," not "5 sessions out"), since it only reserves x-axis width
  for timestamps it's actually seen. Fixed via weekday-stepping (skip
  Sat/Sun) plus whitespace points for the 4 intermediate sessions — still
  exactly one predicted value and one line (Decision 8 unchanged), only
  its axis position corrected.
- **Ticker freshness display**: chips originally showed the literal words
  "Fresh"/"Stale"/"Loading" (Decision 10); replaced with a color dot
  (accessible via `aria-label`, per WCAG's color-not-only rule) plus a
  legend row explaining the mapping.
- **Chart reset-zoom**: once a user manually zoomed/panned the chart,
  there was no way back to a fitted view without reselecting the ticker.
  Added a reset button that restores both the time scale and price scale
  — including fixing a z-index conflict with lightweight-charts' own
  internal canvases that initially made the button unclickable.
- **Default chart zoom**: opening a ticker used to fit the entire
  750-session history into one view, squeezing recent candles (and the
  predicted point) into a thin sliver at the right edge. Now opens on the
  most recent ~60 sessions (~3 months) instead, with the full history
  still reachable by zooming out.
- **Chip layout stability**: the freshness dot's Loading state (a
  differently-sized spinner ring) caused every chip to visibly resize
  the moment its freshness query settled. Fixed with a fixed-footprint
  dot across all states.

None of these change the domain-rule interactions above — Rule 2's
percentage conversion, Rule 6's single-point/no-interpolation chart
constraint (Decision 8), and Rule 4/5's Confidence/Sentiment computation
are all unaffected; these are display-layer fixes to how existing,
already-compliant data is rendered.

**Domain rule interactions:**

- **Rule 1** (target = 5-session log return): unaffected. M5 only
  consumes `predicted_log_return` from the existing `/prediction`
  contract; no change to how the target is computed.
- **Rule 2** (never show raw log return in the UI): honored — the
  frontend converts `predicted_log_return` to a simple percentage before
  rendering, in both the prediction display and the chart's single
  predicted point. The backend contract is unchanged; the raw log return
  remains a legitimate API-layer value, conversion is a display-layer
  responsibility.
- **Rule 3** (advice thresholds are volatility-relative): honored.
  Advice is computed from `0.5 x rolling_std(returns, 60 sessions)` for
  any loaded ticker — this reads live from the ticker's own price
  history, so it has no training-set dependency and works identically
  for the 9 or a searched-in ticker.
- **Rule 4** (confidence = backtested hit-rate): honored, with an
  explicit scope boundary instead of a fabricated number. The 9
  `TRAINING_TICKERS` get `compute_rolling_hit_rate`'s real value
  (existing M3 code). A searched-in ticker gets `N/A` until a
  single-ticker backtest has actually run for it — Confidence is never
  shown as a number that wasn't computed the way the label claims.
- **Rule 5** ("Market Sentiment" is a technical proxy): honored, and the
  label itself is changed to "Technical Signal" with RSI/MACD/Ichimoku
  named inline (not a hover-only disclosure) to make the distinction
  from real sentiment visible without extra interaction.
- **Rule 6** (never frame output as investment advice): honored via
  three mechanisms, replacing the original "restrict prediction display
  to the 9" mitigation (dropped, see below): (a) Advice uses directional
  wording, not BUY/SELL, so nothing on the panel reads as a transaction
  instruction; (b) the disclaimer is unconditional, with no visibility
  toggle; (c) the chart's forecast rendering is a single point + straight
  line, never an interpolated curve, so it never visually overclaims
  confidence in a trajectory the model didn't produce. Predictions are no
  longer restricted to the 9 tickers — that restriction is replaced by
  Confidence's honest `N/A` state for unvalidated tickers, which was
  judged a more accurate mitigation than hiding the prediction outright
  (see `docs/M5_DASHBOARD_EXPLORE_NOTES.md` for the discussion).

## Capabilities

### New Capabilities

- `ticker-catalog`: Serves the fixed set of tickers the model supports,
  with each ticker's data-load status, so the frontend can populate a
  ticker panel without duplicating `TRAINING_TICKERS`.
- `ticker-history`: Serves a bounded trailing OHLCV window for a ticker,
  for chart rendering.
- `ai-insight-panel`: Computes and serves Confidence (`compute_rolling_
  hit_rate` for the 9, `N/A` otherwise), Sentiment (technical proxy,
  live per-ticker), and Advice (volatility-relative, directional
  wording) for a loaded ticker, plus the unconditional disclaimer. First
  change to implement the contract described in `openspec/config.yaml`'s
  AI insight panel section.
- `single-ticker-backtest`: Runs a scoped-down walk-forward backtest for
  one ticker outside `TRAINING_TICKERS`, gated on a minimum
  clean+labeled row count, so `compute_rolling_hit_rate` has real data
  to read for that ticker afterward. Persists into the same
  `backtest_predictions` table M3's training job uses.
- `dashboard-ui`: The Vite/React dashboard itself — ticker panel (chips +
  search), chart panel, prediction display, and the AI insight panel —
  and how it consumes the ticker-catalog, ticker-history,
  ticker-data-ingestion, ticker-prediction, ai-insight-panel, and
  single-ticker-backtest capabilities together.

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
  its return value. New endpoint(s) for the AI insight panel
  (Confidence/Sentiment/Advice) and for triggering a single-ticker
  backtest — both read/write the existing `backtest_predictions` table,
  no new tables required. No schema changes beyond that.
- **Frontend**: net-new `frontend/` tree (Vite + React + React Query),
  currently empty.
- **Dependencies**: adds `@tanstack/react-query` (or current package
  name) and a charting library to `frontend/package.json` (charting
  library choice deferred to design.md).
- **Docs**: `docs/DISCLAIMER.md` is **created by this change** — this is
  the first change to render Advice, Confidence, or Sentiment in the UI,
  so Rule 6's disclaimer requirement is no longer deferrable.
  `docs/DATA_DICTIONARY.md` and `docs/MODEL_CARD.md` need no changes (no
  new columns, no model change).
