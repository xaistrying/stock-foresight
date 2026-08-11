## 1. Backend: ticker catalog endpoint

- [x] 1.1 Add `GET /tickers` route in `backend/app/api/tickers.py`,
      importing `TRAINING_TICKERS` from `backend/app/ml/training.py` as
      the ticker set (no duplicate list).
- [x] 1.2 Query the `tickers` table for each `TRAINING_TICKERS` entry and
      build the response: one entry per ticker with `loaded`,
      `features_computed`, `last_loaded_at` (null/false-equivalent when
      no `tickers` row exists).
- [x] 1.3 Register the route on the existing `tickers_router` in
      `backend/app/main.py` (no new router needed).
- [x] 1.4 Tests in `backend/tests/test_tickers_api.py`: response contains
      exactly `TRAINING_TICKERS`; never-loaded ticker returns
      not-loaded status without error; loaded ticker reflects its
      `tickers` row; request makes no `vnstock` call and writes no rows.

## 2. Backend: ticker history endpoint

- [x] 2.1 Add `GET /tickers/{ticker}/history` route in
      `backend/app/api/tickers.py` (or a new module if `tickers.py`
      grows unwieldy — implementer's call, keep it colocated with the
      other ticker read endpoints if reasonable).
- [x] 2.2 Define the 300-session window as a named constant; query
      `ohlcv` for the most recent 300 rows for the ticker, ordered oldest
      to newest, returning only `date, open, high, low, close, volume`
      (no indicator columns, no `near_gap`).
- [x] 2.3 Return `404` when the ticker has zero rows in `ohlcv`; do not
      call `load_ticker` or any `vnstock` function from this endpoint.
- [x] 2.4 Tests in `backend/tests/test_tickers_api.py` (or a new
      `test_ticker_history_api.py`): >300-row ticker returns exactly the
      300 most recent rows in ascending order; <300-row ticker returns
      all rows without error; never-loaded ticker returns 404 with no
      side effect; response rows never contain an indicator column or
      `near_gap`; a loaded ticker outside `TRAINING_TICKERS` still gets a
      200.

## 3. Backend: explicit load status field

- [x] 3.1 Add a `status` field (`"ok"` / `"rate_limited"` /
      `"invalid_symbol"` / `"no_data"`) to `load_ticker`'s return value
      — already implemented via the `_classify_load_error` helper plus
      the `(ValueError, RetryError)` catch and unwrap (design.md
      Decision 7); this task is to confirm it's present, not to add it
      fresh.
- [x] 3.2 Confirm `load_ticker_endpoint` in `backend/app/api/tickers.py`
      passes the new field through unchanged (it already returns
      `load_ticker`'s dict as-is).
- [x] 3.3 Tests in `backend/tests/test_ticker_ingestion.py`: added
      `test_rate_limit_reports_status_rate_limited`,
      `test_invalid_symbol_format_reports_status_invalid_symbol`,
      `test_invalid_symbol_length_reports_status_invalid_symbol`,
      `test_well_formed_ticker_with_no_data_reports_status_no_data`
      (mocked `RetryError` via a `_FakeLastAttempt` stand-in for
      tenacity's `Future`), `test_unrecognized_value_error_is_not_misclassified`,
      `test_successful_load_reports_status_ok`. All 16 tests in the file
      pass (`pytest backend/tests` — 52 passed overall).

## 4. Backend: AI insight endpoint (Confidence, Sentiment, Advice)

- [x] 4.1 Add `GET /tickers/{ticker}/insight` (or fold into the existing
      prediction route — implementer's call) returning `confidence_score`
      (nullable — `null` when `compute_rolling_hit_rate` returns `None`),
      `confidence_basis` (a string naming the hit-rate window, or naming
      why it's null), `sentiment_proxy`, `sentiment_inputs` (which of
      RSI/MACD/Ichimoku drove the value), `advice_text` (directional
      wording, never "BUY"/"SELL"), matching the response contract in
      `openspec/config.yaml`.
- [x] 4.2 Confidence: call the existing `compute_rolling_hit_rate`
      (`backend/app/ml/backtest.py`) for the ticker; pass its value (or
      `None`) straight through — do not fabricate or substitute a pooled
      value when it's `None` (Rule 4, dashboard-ui spec's "N/A never
      substitutes" requirement).
- [x] 4.3 Sentiment: compute the technical proxy from RSI/MACD/Ichimoku
      position on the ticker's own persisted `features` row — works
      identically for any ticker, no `TRAINING_TICKERS` dependency.
- [x] 4.4 Advice: compute `0.5 x rolling_std(returns, 60 sessions)` on the
      ticker's own OHLCV, compare against the predicted move, and map to
      `"HOLD"` / `"up"` / `"down"` — never a BUY/SELL string.
- [x] 4.5 Tests in `backend/tests/test_ai_insight_api.py`: a
      `TRAINING_TICKERS` ticker with backtest rows returns a real
      `confidence_score`; a ticker with zero `backtest_predictions` rows
      returns `confidence_score: null` with a non-null `confidence_basis`
      explaining why; `sentiment_proxy`/`advice_text` compute for a
      ticker outside `TRAINING_TICKERS` without error; `advice_text`
      never contains the literal strings "BUY" or "SELL" across a range
      of synthetic predicted-move fixtures.

## 5. Backend: single-ticker backtest endpoint

- [x] 5.1 Add `POST /tickers/{ticker}/backtest`, gated on the ticker
      having at least the minimum clean+labeled feature-row count needed
      to form a walk-forward fold (design.md Decision 12 — pick the
      threshold empirically by checking what reliably produces non-empty
      folds via `compute_fold_boundaries` / `run_walk_forward_backtest`
      against a single ticker's data; document the chosen value in this
      task's implementation notes once picked). Return `409` (or similar)
      below the threshold rather than attempting a degenerate backtest.
      **Threshold chosen: `SINGLE_TICKER_BACKTEST_MIN_ROWS = 30`**
      clean+labeled rows (`backend/app/ml/backtest.py`) — verified
      empirically (script run against `compute_fold_boundaries`/
      `purge_training_rows` with `N_FOLDS=5`, both a gap-free sequence and
      one with near_gap rows realistically interspersed) that 30 is the
      smallest count reliably producing all 4 non-empty folds; 25 dropped
      to 3/4 non-empty in both cases.
- [x] 5.2 Implement a single-ticker variant of
      `run_walk_forward_backtest` (`backend/app/ml/backtest.py`) —
      reuses the existing fold/purge logic against one ticker's
      `features` rows instead of the pooled 9-ticker frame.
- [x] 5.3 Persist results via the existing `persist_backtest_predictions`
      into the same `backtest_predictions` table the M3 training job
      writes, so a subsequent `GET /tickers/{ticker}/insight` call's
      `compute_rolling_hit_rate` reflects real data with no separate read
      path.
- [x] 5.4 Tests in `backend/tests/test_single_ticker_backtest.py`: a
      ticker below the row threshold gets a `409`/gated response, not an
      attempted backtest; a ticker above the threshold gets persisted
      `backtest_predictions` rows afterward; `compute_rolling_hit_rate`
      for that ticker returns non-`None` after the backtest completes
      where it returned `None` before. All 3 tests pass; full suite
      (`pytest backend/tests`) is 78 passed.

## 6. Frontend: project scaffold

- [ ] 6.1 Scaffold `frontend/` with Vite + React (npm) per
      `openspec/config.yaml`'s stated stack.
- [ ] 6.2 Add `@tanstack/react-query` and set up a `QueryClientProvider`
      at the app root.
- [ ] 6.3 Choose and add a charting library that can render OHLC candles
      from the `/history` response shape, plus a single additional point
      series for the t+5 prediction (design.md Decision 6 — candidates
      include lightweight-charts, Recharts, visx; confirm no paid license
      required and that it supports a sparse/single-point overlay series
      without interpolating between points).
- [ ] 6.4 Create `frontend/src/api/` client functions for `GET /tickers`,
      `GET /tickers/{ticker}/history`, `GET /tickers/{ticker}/prediction`,
      `GET /tickers/{ticker}/insight`, `POST /tickers/{ticker}/load`,
      `POST /tickers/{ticker}/backtest`, typed to each endpoint's actual
      response shape (including the ok/near_gap/404/5xx variants for
      prediction and the ok/rate_limited/invalid_symbol/no_data variants
      for load).
- [ ] 6.5 Surface `/load`'s `status` field distinctly, now reachable from
      both a chip click and search: `"rate_limited"` (retry-suggesting
      message); `"invalid_symbol"` (now genuinely reachable via search,
      per design.md Decision 3 revised — show a message naming the
      symbol as unrecognized, not a generic failure); `"no_data"`
      (distinct, non-retry-suggesting message — retrying is unlikely to
      help for a well-formed symbol with no real data).
- [ ] 6.6 Add `frontend/src/{components,pages,hooks}/` per the repo's
      stated structure.

## 7. Frontend: ticker panel (chips + search)

- [ ] 7.1 Build the ticker panel component consuming `GET /tickers` via
      React Query — renders one chip per ticker in the response, always
      visible.
- [ ] 7.2 Add a search input that resolves a typed ticker symbol: if
      already selectable (a chip or a previously searched-in ticker),
      select it directly; otherwise call `POST /tickers/{ticker}/load`
      via a React Query mutation and add the ticker to the selectable
      list on success (dashboard-ui spec: "Ticker panel shows the fixed
      set plus search for any real ticker").
- [ ] 7.3 Show per-ticker load status (not-loaded / loaded /
      features-computation-failed) using the status fields from `GET
      /tickers`, or from the searched-in ticker's own load response.
- [ ] 7.4 Show per-ticker freshness state — Loading / Fresh / Stale
      (dashboard-ui spec) — comparing the ticker's stored prediction
      `as_of` against the latest trading session available in its data,
      not a fixed calendar-age threshold.
- [ ] 7.5 On a successful load (chip or search), immediately trigger that
      ticker's prediction request too (no separate user action) and
      invalidate/refetch `/prediction`, `/history`, and `/insight` for
      it.
- [ ] 7.6 Surface load-in-progress and load-failure states distinctly.
      Reachable failure status values from `/load` now include
      `"rate_limited"`, `"invalid_symbol"` (reachable via search, not
      only a theoretical case), and `"no_data"` — each with its own
      message (retry-suggesting for `rate_limited`, symbol-specific for
      `invalid_symbol`, non-retry-suggesting for `no_data`). Separately,
      still handle a non-2xx/network-level failure with no parseable
      `status` field (a generic "something went wrong" message) for
      failures below the `status`-classification layer.

## 8. Frontend: chart panel

- [ ] 8.1 Build the chart panel component consuming `GET
      /tickers/{ticker}/history` via React Query for the currently
      selected ticker.
- [ ] 8.2 Render OHLC candles only from `/history` — no indicator
      overlay (Ichimoku/RSI/MACD/Bollinger/ATR/OBV).
- [ ] 8.3 When the selected ticker's prediction has `status: "ok"`,
      render exactly one additional point at the t+5 position (from
      `predicted_log_return`, converted to a percentage/price per Rule
      2), joined to the most recent historical close by a single
      straight line — no interpolated or smoothed intermediate points
      (dashboard-ui spec: "Chart panel renders OHLCV plus the single
      predicted point"). Omit the point entirely for `near_gap`, `404`,
      or `5xx` prediction states.
- [ ] 8.4 Handle the 404 (never-loaded) and loading states distinctly
      (e.g. empty-state prompting the user to load the ticker first).

## 9. Frontend: prediction display

- [ ] 9.1 Build the prediction display component consuming `GET
      /tickers/{ticker}/prediction` via React Query.
- [ ] 9.2 Implement the log-return-to-percentage conversion (`(e^x - 1) *
      100`) as a single shared utility function; the raw
      `predicted_log_return` value must not reach any render path
      unconverted (Rule 2) — reused by both the prediction display and
      the chart panel's single point (task 8.3).
- [ ] 9.3 Render four visually distinct states: `status: "ok"`
      (percentage + `as_of` + static "5 trading sessions" label text —
      never a horizon-adjustment control, per design.md Decision 9),
      `status: "near_gap"`, `404` (not-loaded), `5xx` (feature
      computation failed) — no shared generic/blank state across more
      than one of these.

## 10. Frontend: AI insight panel

- [ ] 10.1 Build the AI insight panel component consuming `GET
      /tickers/{ticker}/insight` via React Query, for any loaded ticker
      — this replaces the earlier placeholder entirely; there is no
      "coming soon" state to build.
- [ ] 10.2 Confidence: render `confidence_score` as a percentage with
      subtext naming it as a hit-rate over the ticker's most recent
      backtested predictions, when non-null. When `confidence_score` is
      `null`, render an explicit `N/A` with `confidence_basis`'s
      explanatory text — never a fabricated or substituted percentage
      (dashboard-ui spec: "N/A never substitutes a pooled or global
      value").
- [ ] 10.3 When Confidence is `N/A`, show the "Backtest this ticker"
      action per the gate `GET /tickers/{ticker}/backtest`'s response
      (or a client-side row-count check against `/insight`'s data, if
      the gate is exposed there — implementer's call which layer owns
      the threshold check, but the UI-visible behavior must match
      dashboard-ui spec's "Action is offered once there is enough
      history"). Calling `POST /tickers/{ticker}/backtest` shows a
      disabled, loading state on the action only, leaving Prediction,
      Sentiment, and Advice interactive; on completion, refetch
      `/insight` so Confidence displays the real value.
- [ ] 10.4 Sentiment: label it "Technical Signal" (never "Market
      Sentiment"), and always show `sentiment_inputs` (RSI/MACD/Ichimoku)
      inline as visible text, not behind a tooltip or hover (Rule 5).
- [ ] 10.5 Advice: render `advice_text` with the preceding reasoning line
      (e.g. "Move is within normal volatility range" / "Move exceeds
      typical volatility to the upside/downside") followed by the
      directional verdict ("HOLD" / "Signal: up" / "Signal: down") —
      confirm no component or copy path can render "BUY" or "SELL"
      (Rules 3, 6).
- [ ] 10.6 Disclaimer: render the disclaimer text unconditionally
      alongside Confidence/Sentiment/Advice, with no toggle, setting, or
      collapse control anywhere in the UI that could hide it (Rule 6).
      Use the copy drafted in `docs/M5_DASHBOARD_EXPLORE_NOTES.md`'s
      copy contract as the actual shipped text, and create
      `docs/DISCLAIMER.md` (this is the first change to render
      Advice/Confidence/Sentiment — Rule 6 requires the doc to exist from
      here on).

## 11. Frontend: dashboard assembly

- [ ] 11.1 Compose ticker panel (chips + search), chart panel, prediction
      display, and the AI insight panel into the dashboard page/layout,
      wired so selecting a ticker (via chip or search) drives the chart,
      prediction display, and AI insight panel for that same ticker.
- [ ] 11.2 Verify the load → auto-predict → invalidate → refetch flow end
      to end for both entry points: clicking an unloaded chip, and
      searching a ticker not yet in the DB — both update the chart,
      prediction display, and AI insight panel without a manual page
      refresh or a separate action to request the prediction.
- [ ] 11.3 Confirm the top of the dashboard carries no leftover
      horizon-adjustment, advice-style, or disclaimer-visibility control
      (design.md Decision 9) — these were considered from the reference
      screenshot and explicitly dropped, not just unimplemented.

## 12. Verification

- [ ] 12.1 `pytest backend/tests` passes, including the new tests from
      sections 1-5.
- [ ] 12.2 `cd frontend && npm run test` passes for any frontend tests
      added alongside components 7-10.
- [ ] 12.3 Manual pass: for at least one ticker in each of the four
      prediction states (ok, near_gap, not-loaded, feature-failed —
      simulate the latter two via test data if not naturally available)
      confirm the dashboard shows the correct distinct UI state and no
      raw log return value appears anywhere, including dev tools/DOM
      inspection, in either the prediction display or the chart's single
      point.
- [ ] 12.4 Manual pass: trigger (or simulate) a `rate_limited` load
      outcome, an `invalid_symbol` outcome (via search, e.g. a malformed
      symbol string), and a `no_data` outcome; confirm the panel shows
      three distinct messages, none collapsed into another or into the
      generic network-error case.
- [ ] 12.5 Manual pass: search a real ticker outside `TRAINING_TICKERS`
      that has never been loaded; confirm it loads, predicts
      automatically, charts, and shows Sentiment/Advice normally, while
      Confidence shows `N/A` with the "Backtest this ticker" action
      (enabled or explained-as-disabled depending on available history).
      If enough history exists, trigger the backtest and confirm
      Confidence transitions to a real percentage afterward.
- [ ] 12.6 Manual pass: confirm the disclaimer is visible for every
      ticker state that shows Confidence/Sentiment/Advice, and that no
      control anywhere hides it; confirm Advice never renders "BUY" or
      "SELL" across a HOLD case and both directional cases.
