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
- [x] 2.5 (Post-ship, 2026-08-12) Widen `HISTORY_WINDOW_SESSIONS` from
      300 to 750 sessions (~3 years) in `backend/app/api/tickers.py`, per
      design.md Decision 2 revised — the original 300-session window
      read as too little visible chart history in real use. Update
      `test_tickers_api.py`/`test_ticker_history_api.py`'s row-count
      assertions (2.4) from 300 to 750 accordingly. No response shape
      change — same fields, same ordering, just a larger fixed constant.
      `test_tickers_api.py`'s row-count assertions already referenced the
      live `tickers_api.HISTORY_WINDOW_SESSIONS` constant symbolically,
      not a hardcoded `300` literal, so they needed no numeric change —
      only renamed
      `test_history_returns_300_most_recent_rows_ascending_when_more_stored`
      to drop the now-stale "300" from its name. Full backend suite:
      `pytest backend/tests` — 78 passed.

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

- [x] 6.1 Scaffold `frontend/` with Vite + React (npm) per
      `openspec/config.yaml`'s stated stack.
- [x] 6.2 Add `@tanstack/react-query` and set up a `QueryClientProvider`
      at the app root.
- [x] 6.3 Choose and add a charting library that can render OHLC candles
      from the `/history` response shape, plus a single additional point
      series for the t+5 prediction (design.md Decision 6 — candidates
      include lightweight-charts, Recharts, visx; confirm no paid license
      required and that it supports a sparse/single-point overlay series
      without interpolating between points).
      **Chosen: `lightweight-charts` v5.2.0 (Apache-2.0, TradingView,
      actively maintained)** — native candlestick series for `/history`,
      plus a separate line series can hold a single two-point segment
      (last close -> predicted point) without interpolating beyond those
      two points, satisfying Decision 8.
- [x] 6.4 Create `frontend/src/api/` client functions for `GET /tickers`,
      `GET /tickers/{ticker}/history`, `GET /tickers/{ticker}/prediction`,
      `GET /tickers/{ticker}/insight`, `POST /tickers/{ticker}/load`,
      `POST /tickers/{ticker}/backtest`, typed to each endpoint's actual
      response shape (including the ok/near_gap/404/5xx variants for
      prediction and the ok/rate_limited/invalid_symbol/no_data variants
      for load).
- [x] 6.5 Surface `/load`'s `status` field distinctly, now reachable from
      both a chip click and search: `"rate_limited"` (retry-suggesting
      message); `"invalid_symbol"` (now genuinely reachable via search,
      per design.md Decision 3 revised — show a message naming the
      symbol as unrecognized, not a generic failure); `"no_data"`
      (distinct, non-retry-suggesting message — retrying is unlikely to
      help for a well-formed symbol with no real data).
- [x] 6.6 Add `frontend/src/{components,pages,hooks}/` per the repo's
      stated structure.

## 7. Frontend: ticker panel (chips + search)

- [x] 7.1 Build the ticker panel component consuming `GET /tickers` via
      React Query — renders one chip per ticker in the response, always
      visible.
- [x] 7.2 Add a search input that resolves a typed ticker symbol: if
      already selectable (a chip or a previously searched-in ticker),
      select it directly; otherwise call `POST /tickers/{ticker}/load`
      via a React Query mutation and add the ticker to the selectable
      list on success (dashboard-ui spec: "Ticker panel shows the fixed
      set plus search for any real ticker").
- [x] 7.3 Show per-ticker load status (not-loaded / loaded /
      features-computation-failed) using the status fields from `GET
      /tickers`, or from the searched-in ticker's own load response.
- [x] 7.4 Show per-ticker freshness state — Loading / Fresh / Stale
      (dashboard-ui spec) — comparing the ticker's stored prediction
      `as_of` against the latest trading session available in its data,
      not a fixed calendar-age threshold.
- [x] 7.5 On a successful load (chip or search), immediately trigger that
      ticker's prediction request too (no separate user action) and
      invalidate/refetch `/prediction`, `/history`, and `/insight` for
      it.
- [x] 7.6 Surface load-in-progress and load-failure states distinctly.
      Reachable failure status values from `/load` now include
      `"rate_limited"`, `"invalid_symbol"` (reachable via search, not
      only a theoretical case), and `"no_data"` — each with its own
      message (retry-suggesting for `rate_limited`, symbol-specific for
      `invalid_symbol`, non-retry-suggesting for `no_data`). Separately,
      still handle a non-2xx/network-level failure with no parseable
      `status` field (a generic "something went wrong" message) for
      failures below the `status`-classification layer.
- [x] 7.7 (Post-ship, 2026-08-12) Replace each chip's visible
      "Fresh"/"Stale"/"Loading" text (7.4) with a color dot plus a legend
      row below the chip list explaining the color mapping, per design.md
      Decision 16 — the words took up disproportionate horizontal space
      once every chip carried one. The dot carries an `aria-label`/`title`
      with the same wording the text used, so the state stays reachable
      by hover/screen reader (WCAG color-not-only) even though it's no
      longer always-visible text. Load-failure/not-loaded/feature-failed
      messages are unaffected — those remain visible text. Also fixed
      (Decision 19): the Loading spinner and the resting Fresh/Stale dot
      were different sizes (0.75rem vs 0.5rem), so every chip visibly
      resized the moment its freshness query settled from Loading to its
      final state — unified to a fixed 0.75rem box across all states.

## 8. Frontend: chart panel

- [x] 8.1 Build the chart panel component consuming `GET
      /tickers/{ticker}/history` via React Query for the currently
      selected ticker.
- [x] 8.2 Render OHLC candles only from `/history` — no indicator
      overlay (Ichimoku/RSI/MACD/Bollinger/ATR/OBV).
- [x] 8.3 When the selected ticker's prediction has `status: "ok"`,
      render exactly one additional point at the t+5 position (from
      `predicted_log_return`, converted to a percentage/price per Rule
      2), joined to the most recent historical close by a single
      straight line — no interpolated or smoothed intermediate points
      (dashboard-ui spec: "Chart panel renders OHLCV plus the single
      predicted point"). Omit the point entirely for `near_gap`, `404`,
      or `5xx` prediction states.
      **Note**: the backend's `/prediction` response only returns
      `as_of` (the date the prediction was made *from*), never a t+5
      target date — Rule 1 fixes the horizon at 5 *trading sessions*,
      not calendar days, and `/history` has no future rows to count real
      sessions against. Resolved with the user: the predicted point's
      x-position uses `as_of + 7 calendar days` as an approximation
      (`approximateTargetDate` in `frontend/src/lib/logReturn.js`) — a
      visual placement heuristic only; it does not affect the predicted
      *value* (Rule 2's percentage/price conversion is exact).
- [x] 8.4 Handle the 404 (never-loaded) and loading states distinctly
      (e.g. empty-state prompting the user to load the ticker first).
- [x] 8.5 (Post-ship, 2026-08-12) Fix the t+5 predicted point's x-axis
      placement (8.3's `+7 calendar days` approximation) — real usage
      found it rendered immediately adjacent to the last candle, reading
      as "tomorrow" rather than "5 sessions out," because
      lightweight-charts' time scale only reserves x-axis width for
      timestamps it has actually been given data for. Per design.md
      Decision 15: `approximateTargetDate` now steps forward 5 weekdays
      (skipping Sat/Sun) instead of a flat 7 calendar days, and the chart
      also passes the 4 intermediate weekday dates as lightweight-charts
      "whitespace" points (`{time}`, no `value`) to reserve the axis
      space — these are never plotted or connected by the line, so 8.3's
      "exactly one predicted point, no interpolation" constraint is
      unchanged; only the point's x-position is corrected.
- [x] 8.6 (Post-ship, 2026-08-12) Add a "Reset zoom" control and change
      the default zoom on ticker selection, per design.md Decisions 17-18:
      (a) a small icon button (top-right of the chart canvas) that
      restores both the time scale (`fitContent()`/default window) and
      the price scale (`setAutoScale(true)`) after a user manually
      pans/zooms either axis — fixed a lightweight-charts internal
      `z-index: 2` on its own canvases that initially made the button
      unclickable despite rendering correctly, by raising the button to
      `z-index: 3`; (b) opening a ticker (or clicking Reset zoom) now
      shows the most recent 60 sessions via
      `timeScale().setVisibleLogicalRange()` instead of fitting the
      entire 750-session history (task 2.5) into one view, which
      squeezed recent candles and the predicted point into a thin sliver
      at the right edge. Falls back to `fitContent()` when a ticker has
      fewer than 60 sessions of history.

## 9. Frontend: prediction display

- [x] 9.1 Build the prediction display component consuming `GET
      /tickers/{ticker}/prediction` via React Query.
      Built `frontend/src/components/PredictionDisplay/PredictionDisplay.jsx`,
      consuming the existing `useTickerPrediction` hook (task 8's hook,
      reused as-is).
- [x] 9.2 Implement the log-return-to-percentage conversion (`(e^x - 1) *
      100`) as a single shared utility function; the raw
      `predicted_log_return` value must not reach any render path
      unconverted (Rule 2) — reused by both the prediction display and
      the chart panel's single point (task 8.3).
      `logReturnToPercent` already existed in `frontend/src/lib/logReturn.js`
      (added alongside task 8.3's `logReturnToPrice`); `PredictionDisplay`
      calls it rather than adding a second implementation.
- [x] 9.3 Render four visually distinct states: `status: "ok"`
      (percentage + `as_of` + static "5 trading sessions" label text —
      never a horizon-adjustment control, per design.md Decision 9),
      `status: "near_gap"`, `404` (not-loaded), `5xx` (feature
      computation failed) — no shared generic/blank state across more
      than one of these.
      Also retains an empty (`!ticker`), loading, and generic-error (a
      non-404/5xx `ApiError`) state for parity with the chart panel's
      state handling, though only the four listed above are required by
      the spec. Tests in
      `frontend/src/components/PredictionDisplay/PredictionDisplay.test.jsx`
      (8 tests) cover: empty, loading, ok-with-positive-percent (asserting
      the raw log return string never appears), ok-with-negative-percent,
      near_gap (no percentage shown), 404, 5xx, and that all three failure
      states render distinct text. Full frontend suite: `npm run test`
      — 40 passed across 7 files. `npm run lint` clean.

## 10. Frontend: AI insight panel

- [x] 10.1 Build the AI insight panel component consuming `GET
      /tickers/{ticker}/insight` via React Query, for any loaded ticker
      — this replaces the earlier placeholder entirely; there is no
      "coming soon" state to build.
      Built `frontend/src/components/AIInsightPanel/AIInsightPanel.jsx`,
      backed by a new `useTickerInsight` hook
      (`frontend/src/hooks/useTickerInsight.js`, mirrors
      `useTickerPrediction`'s shape). Distinct empty / loading / 404
      (not-loaded) / 5xx (feature-computation-failed) / generic-error
      states precede the real Confidence/Sentiment/Advice render, matching
      the other panels' state-handling convention.
- [x] 10.2 Confidence: render `confidence_score` as a percentage with
      subtext naming it as a hit-rate over the ticker's most recent
      backtested predictions, when non-null. When `confidence_score` is
      `null`, render an explicit `N/A` with `confidence_basis`'s
      explanatory text — never a fabricated or substituted percentage
      (dashboard-ui spec: "N/A never substitutes a pooled or global
      value").
      `confidence_basis` is rendered verbatim from the API response in
      both branches (real value and `N/A`) rather than a second hardcoded
      copy of that text, so the two never drift.
- [x] 10.3 When Confidence is `N/A`, show the "Backtest this ticker"
      action per the gate `GET /tickers/{ticker}/backtest`'s response
      (or a client-side row-count check against `/insight`'s data, if
      the gate is exposed there — implementer's call which layer owns
      the threshold check, but the UI-visible behavior must match
      dashboard-ui spec's "Action is offered once there is enough
      history"). Calling `POST /tickers/{ticker}/backtest` shows a
      disabled, loading state on the action only, leaving Prediction,
      Sentiment, and Advice interactive; on completion, refetch
      `/insight` so Confidence displays the real value.
      **Implementer's call**: there is no separate read-only gate-check
      endpoint — `SINGLE_TICKER_BACKTEST_MIN_ROWS` is enforced only inside
      `POST /tickers/{ticker}/backtest` itself (409 below threshold). New
      `useBacktestTicker` hook
      (`frontend/src/hooks/useBacktestTicker.js`) always offers the
      action when Confidence is `N/A`; the backtest call *is* the
      threshold check, and a 409 renders as "Needs more price history to
      backtest…" explanatory text (via `mutation.isBelowThreshold`)
      instead of a generic failure — satisfying the spec's UI-visible
      behavior without a client-side row-count duplicate of the backend's
      gate. On success, invalidates the ticker's `/insight` query so
      Confidence refetches the real value with no distinct "just
      backtested" visual state, per design.md Decision 12. Prediction and
      the rest of the AI insight panel (Sentiment/Advice) render
      independently of this mutation's state, so they stay interactive
      while a backtest runs.
- [x] 10.4 Sentiment: label it "Technical Signal" (never "Market
      Sentiment"), and always show `sentiment_inputs` (RSI/MACD/Ichimoku)
      inline as visible text, not behind a tooltip or hover (Rule 5).
      Renders the response's own `sentiment_inputs` array (joined inline),
      not a hardcoded restatement of it, so the basis text can't drift
      from what the backend actually used.
- [x] 10.5 Advice: render `advice_text` with the preceding reasoning line
      (e.g. "Move is within normal volatility range" / "Move exceeds
      typical volatility to the upside/downside") followed by the
      directional verdict ("HOLD" / "Signal: up" / "Signal: down") —
      confirm no component or copy path can render "BUY" or "SELL"
      (Rules 3, 6).
      `advice_text` from the backend is the raw enum value
      (`"HOLD"`/`"up"`/`"down"`); a fixed `ADVICE_COPY` lookup (sourced
      from `docs/M5_DASHBOARD_EXPLORE_NOTES.md`'s copy contract) maps each
      to its reasoning + verdict pair. No `advice_text` value maps to
      "BUY" or "SELL" — confirmed by test assertions searching rendered
      output for both literal strings. Advice section is omitted entirely
      when `advice_text` is `null` (the near_gap case), showing the
      response's `note` text instead.
- [x] 10.6 Disclaimer: render the disclaimer text unconditionally
      alongside Confidence/Sentiment/Advice, with no toggle, setting, or
      collapse control anywhere in the UI that could hide it (Rule 6).
      Use the copy drafted in `docs/M5_DASHBOARD_EXPLORE_NOTES.md`'s
      copy contract as the actual shipped text, and create
      `docs/DISCLAIMER.md` (this is the first change to render
      Advice/Confidence/Sentiment — Rule 6 requires the doc to exist from
      here on).
      Created `docs/DISCLAIMER.md` with both the inline and full-version
      copy verbatim from the explore notes. The inline sentence renders
      unconditionally at the bottom of every non-loading/non-empty
      `AIInsightPanel` state (including near_gap, where Advice itself is
      absent) — there is no prop, state, or control anywhere in the
      component that can hide it. Tests in
      `frontend/src/components/AIInsightPanel/AIInsightPanel.test.jsx`
      (13 tests) cover: empty, loading, 404, 5xx, real Confidence,
      N/A Confidence + Backtest action, backtest in-flight (panel stays
      interactive), backtest 409 (distinct "needs more history" text),
      Sentiment labeling + inputs, Advice up/HOLD wording with no BUY/SELL
      anywhere, unconditional disclaimer with no toggle/checkbox/switch
      role present, and near_gap (no Advice section, disclaimer still
      shown). Full frontend suite: `npm run test` — 53 passed across 8
      files. `npm run lint` clean.

## 11. Frontend: dashboard assembly

- [x] 11.1 Compose ticker panel (chips + search), chart panel, prediction
      display, and the AI insight panel into the dashboard page/layout,
      wired so selecting a ticker (via chip or search) drives the chart,
      prediction display, and AI insight panel for that same ticker.
      `frontend/src/App.jsx` now renders all four panels, all keyed off
      one `selectedTicker` state: `TickerPanel` (chips + search) on top,
      `ChartPanel` + a `PredictionDisplay`/`AIInsightPanel` side column
      below (`App.css`'s new `.app-shell__main`/`.app-shell__side` grid,
      responsive single-column below 800px). Also replaced `index.css`'s
      leftover Vite-template rules (fixed-width, centered, bordered
      `#root`, unused heading/code styles) with a minimal reset — those
      conflicted with the dashboard's own layout and tokens once real
      panels were assembled here, so removed rather than carried forward
      unused.
- [x] 11.2 Verify the load → auto-predict → invalidate → refetch flow end
      to end for both entry points: clicking an unloaded chip, and
      searching a ticker not yet in the DB — both update the chart,
      prediction display, and AI insight panel without a manual page
      refresh or a separate action to request the prediction.
      Verified via new `frontend/src/App.test.jsx` integration tests
      against the real composed tree (no props injected directly into
      child panels): (1) selecting an already-loaded chip renders the
      chart/prediction/insight for that ticker; (2) clicking an unloaded
      chip triggers `/load`, then `fetchTickerPrediction` and
      `fetchTickerInsight` are asserted called for that ticker with no
      separate user action, and the AI insight panel's N/A+Backtest state
      renders; (3) searching a not-yet-loaded ticker (`FPT`) drives the
      same chart/prediction/insight rendering as a chip would. Playwright
      (browser-driven manual check) was attempted but this environment
      has no Chromium binary installed (`chrome not found at
      /opt/google/chrome/chrome`) — deferred to task 12.3's manual pass
      rather than installing a browser as a side effect of this task;
      the integration tests above exercise the same flow through the real
      component tree and React Query cache, just without a real browser
      viewport.
- [x] 11.3 Confirm the top of the dashboard carries no leftover
      horizon-adjustment, advice-style, or disclaimer-visibility control
      (design.md Decision 9) — these were considered from the reference
      screenshot and explicitly dropped, not just unimplemented.
      Confirmed two ways: a dedicated `App.test.jsx` assertion (no
      `slider`/`combobox`/`checkbox`/`switch` role and no "horizon...day"
      text anywhere on the rendered page for a loaded ticker), and a
      repo-wide grep for `horizonDays`/`adviceStyle`/`showDisclaimer`
      turning up only explanatory comments (this task and App.jsx's own
      comment), no actual controls or dead CSS. Full frontend suite:
      `npm run test -- --no-file-parallelism` — 57 passed across 9 files,
      reliably across repeated runs. `npm run lint` and `npm run build`
      both clean. **Note**: plain `npm run test` (file-parallel) is
      flaky in this sandbox — one `TickerPanel` test intermittently times
      out waiting on `GET /tickers` under concurrent test-file execution.
      Confirmed pre-existing and environment-level, not caused by this
      session's changes: reproduces with only sections 1-8's code present
      (`git stash`) and disappears entirely with `--no-file-parallelism`,
      so it's resource contention in this sandbox's test runner, not a
      test or component bug. Left as-is rather than restructuring the
      test suite to work around sandbox contention — worth a follow-up if
      it also reproduces in CI.
- [x] 11.4 (Post-ship, 2026-08-12) Remove `.app-shell`'s `max-width:
      72rem; margin: 0 auto` in `App.css` so the dashboard fills the
      viewport width instead of sitting centered in a fixed-width column,
      per design.md Decision 14. Update/add an `App.test.jsx` or visual
      check confirming the shell no longer caps width (e.g. assert no
      `max-width` constraint remains, or a rendered-width check if the
      test setup supports it).
      Removed both declarations from `.app-shell`, keeping its horizontal
      padding so content doesn't touch the viewport edges. Added a new
      `App.test.jsx` test that reads `App.css`'s actual `.app-shell` rule
      text (stripped of comments, since the removed-declaration
      explanation itself mentions "max-width"/"margin: 0 auto" in prose)
      and asserts neither declaration remains — a real rendered-width
      assertion isn't meaningful under jsdom, which doesn't compute
      layout from stylesheets. Verified visually too: took real
      screenshots via Playwright/Chrome (installed in task 12.3) at a
      1920px viewport against the live dev server + backend — the
      dashboard fills the full width edge-to-edge (vs. the previous
      centered ~1152px column), and TCB's chart now shows ~3 years
      (Aug 2023–Jul 2026) after task 2.5's window widening, still
      rendering the real prediction/Confidence/Sentiment/Advice
      correctly at the new width. Full frontend suite:
      `npm run test -- --run --no-file-parallelism` — 58 passed across 9
      files. `npm run lint` and `npm run build` both clean.

## 12. Verification

- [x] 12.1 `pytest backend/tests` passes, including the new tests from
      sections 1-5.
      Ran via the project's `.venv` (`backend/.venv/bin/python -m pytest
      tests`, since `pytest`/`python` aren't on PATH directly in this
      shell): **78 passed** (2 warnings, both pre-existing/unrelated —
      an `httpx` deprecation notice and a `vnai` upgrade notice).
- [x] 12.2 `cd frontend && npm run test` passes for any frontend tests
      added alongside components 7-10.
      `npm run test -- --run --no-file-parallelism`: **57 passed** across
      9 files, reliably across repeated runs. Plain `npm run test` (file-
      parallel) still shows the pre-existing sandbox-contention flake
      documented in task 11.2/11.3 (one `TickerPanel` test times out
      under concurrent file execution) — reconfirmed here, still not
      reproducible in isolation or with parallelism off, so unchanged
      from the prior session's finding.
- [x] 12.3 Manual pass: for at least one ticker in each of the four
      prediction states (ok, near_gap, not-loaded, feature-failed —
      simulate the latter two via test data if not naturally available)
      confirm the dashboard shows the correct distinct UI state and no
      raw log return value appears anywhere, including dev tools/DOM
      inspection, in either the prediction display or the chart's single
      point.
      Ran the real dashboard (Vite dev server + the actual running
      FastAPI backend, no mocks) via Playwright/Chrome — installed for
      this session with `sudo npx playwright install --with-deps chrome`
      after the sandbox initially had no browser binary.
      **`ok` — verified live**: selected TCB, got a real `-1.43%`
      prediction (backend's raw `predicted_log_return:
      -0.01443456206470728`), "As of 2026-07-29", "Fixed horizon: 5
      trading sessions". Checked `document.documentElement.outerHTML`
      and every element attribute for the raw value/any truncation of it
      (`0.01443`, `-0.0144`) — zero matches; no dev-tools-visible leak
      anywhere, confirmed via `browser_evaluate`, not just visual
      inspection.
      **`not-loaded` (404) — verified live indirectly**: confirmed `GET
      /tickers/GAS/prediction` 404s before loading it; the real dashboard
      flow never actually renders this state for a user-selected ticker
      by construction (search auto-loads on submit, per design.md
      Decision 3 revised — `PredictionDisplay`/`AIInsightPanel` only ever
      receive a `ticker` prop after selection, and selection only follows
      a successful load), so the 404 UI treatment itself is verified via
      `PredictionDisplay.test.jsx`/`AIInsightPanel.test.jsx`'s existing
      404 tests rather than a live click path that doesn't exist.
      **`near_gap` and feature-failure (5xx) — verified via existing
      tests, not live**: none of the 9 live tickers currently has a
      `near_gap` feature row or a feature-computation failure, and
      manufacturing either would mean corrupting real rows in the shared
      project DB — not done. Both states are covered by dedicated,
      passing tests (`PredictionDisplay.test.jsx`,
      `AIInsightPanel.test.jsx`) using mocked responses shaped exactly
      like the real API contract.
- [x] 12.4 Manual pass: trigger (or simulate) a `rate_limited` load
      outcome, an `invalid_symbol` outcome (via search, e.g. a malformed
      symbol string), and a `no_data` outcome; confirm the panel shows
      three distinct messages, none collapsed into another or into the
      generic network-error case.
      **`invalid_symbol` — verified live**: searched "XX" (2 chars, below
      vnstock's minimum) — dashboard showed `"XX" isn't a recognized
      ticker symbol.` as a distinct alert, and the already-selected
      TCB's chart/prediction/insight were untouched by the failed search.
      **`no_data` and `rate_limited` — verified via existing tests, not
      live**: tried two well-formed candidate symbols
      (`AAAAAAAAAAAA`, `ZZZ999`) against the live backend hoping to find
      a real no-data case; both actually hit vnstock's own format
      validation and returned `invalid_symbol` instead, so neither
      produced a live `no_data` example without guessing further against
      the real (rate-limited) provider. `rate_limited` isn't something
      that can be triggered on demand at all without deliberately
      hammering the live API past its quota, which risks breaking access
      for the rest of this session and beyond. Both are covered by
      dedicated, passing tests in `TickerPanel.test.jsx` asserting their
      exact, distinct message text (`"...unlikely to help"` for
      `no_data`, `"...try again in a moment"` for `rate_limited`).
- [x] 12.5 Manual pass: search a real ticker outside `TRAINING_TICKERS`
      that has never been loaded; confirm it loads, predicts
      automatically, charts, and shows Sentiment/Advice normally, while
      Confidence shows `N/A` with the "Backtest this ticker" action
      (enabled or explained-as-disabled depending on available history).
      If enough history exists, trigger the backtest and confirm
      Confidence transitions to a real percentage afterward.
      **Fully verified live end to end**, no mocks: searched `GAS`
      (PetroVietnam Gas, real ticker, confirmed 404/never-loaded via the
      API beforehand) — loaded successfully, joined the chip list as
      Fresh, auto-predicted (`-1.23%`, as of 2026-08-12, same day),
      charted, and Sentiment (`Bullish`)/Advice (`Move is within normal
      volatility range` / `HOLD`) rendered normally. Confidence correctly
      showed `N/A` with "Needs more price history to backtest" reasoning
      and an enabled "Backtest this ticker" button (GAS had enough
      clean+labeled rows to clear `SINGLE_TICKER_BACKTEST_MIN_ROWS`).
      Clicked it — the real single-ticker walk-forward backtest ran
      against the live backend, and Confidence transitioned to `83%`
      afterward, rendered identically to a `TRAINING_TICKERS` ticker with
      no distinct "just backtested" visual state, exactly per design.md
      Decision 12.
- [x] 12.6 Manual pass: confirm the disclaimer is visible for every
      ticker state that shows Confidence/Sentiment/Advice, and that no
      control anywhere hides it; confirm Advice never renders "BUY" or
      "SELL" across a HOLD case and both directional cases.
      **Verified live** across every ticker state rendered this session
      (TCB, VND — both `Signal: down`; GAS before and after backtest —
      `HOLD`): the disclaimer sentence ("Technical observation from a
      backtested model — not a forecast, not investment advice.")
      appeared every time, with no toggle/control anywhere near it — and
      a `document.body.innerText` regex scan for `\bBUY\b`/`\bSELL\b`
      across the live-rendered page came back with zero matches. No live
      ticker happened to be in the `up` state at test time (a real
      down-trending moment across the 9 — confirmed by checking
      `advice_text` for all 9 via the API directly), so `Signal: up`'s
      exact copy and disclaimer presence is covered by
      `AIInsightPanel.test.jsx`'s existing passing test for that case
      instead of a live example.
