## 1. Backend: ticker catalog endpoint

- [ ] 1.1 Add `GET /tickers` route in `backend/app/api/tickers.py`,
      importing `TRAINING_TICKERS` from `backend/app/ml/training.py` as
      the ticker set (no duplicate list).
- [ ] 1.2 Query the `tickers` table for each `TRAINING_TICKERS` entry and
      build the response: one entry per ticker with `loaded`,
      `features_computed`, `last_loaded_at` (null/false-equivalent when
      no `tickers` row exists).
- [ ] 1.3 Register the route on the existing `tickers_router` in
      `backend/app/main.py` (no new router needed).
- [ ] 1.4 Tests in `backend/tests/test_tickers_api.py`: response contains
      exactly `TRAINING_TICKERS`; never-loaded ticker returns
      not-loaded status without error; loaded ticker reflects its
      `tickers` row; request makes no `vnstock` call and writes no rows.

## 2. Backend: ticker history endpoint

- [ ] 2.1 Add `GET /tickers/{ticker}/history` route in
      `backend/app/api/tickers.py` (or a new module if `tickers.py`
      grows unwieldy — implementer's call, keep it colocated with the
      other ticker read endpoints if reasonable).
- [ ] 2.2 Define the 300-session window as a named constant; query
      `ohlcv` for the most recent 300 rows for the ticker, ordered oldest
      to newest, returning only `date, open, high, low, close, volume`
      (no indicator columns, no `near_gap`).
- [ ] 2.3 Return `404` when the ticker has zero rows in `ohlcv`; do not
      call `load_ticker` or any `vnstock` function from this endpoint.
- [ ] 2.4 Tests in `backend/tests/test_tickers_api.py` (or a new
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

## 4. Frontend: project scaffold

- [ ] 4.1 Scaffold `frontend/` with Vite + React (npm) per
      `openspec/config.yaml`'s stated stack.
- [ ] 4.2 Add `@tanstack/react-query` and set up a `QueryClientProvider`
      at the app root.
- [ ] 4.3 Choose and add a charting library that can render OHLC candles
      from the `/history` response shape (design.md Decision 6 —
      candidates include lightweight-charts, Recharts, visx; confirm no
      paid license required).
- [ ] 4.4 Create `frontend/src/api/` client functions for `GET
      /tickers`, `GET /tickers/{ticker}/history`, `GET
      /tickers/{ticker}/prediction`, `POST /tickers/{ticker}/load`, typed
      to each endpoint's actual response shape (including the
      ok/near_gap/404/5xx variants for prediction and the
      ok/rate_limited/invalid_symbol/no_data variants for load).
- [ ] 4.5 Surface `/load`'s `status` field distinctly in the panel:
      `"rate_limited"` (retry-suggesting message) is the realistic
      failure mode for this panel's traffic; `"invalid_symbol"` isn't
      reachable in practice (free-text entry isn't offered, per
      Decision 3) but the UI type must still account for all four
      values on the response shape; `"no_data"` is reachable even for a
      fixed, previously-successful ticker if vnstock temporarily has no
      data for it — give it a distinct, non-retry-suggesting message
      (retrying `no_data` is unlikely to help, unlike `rate_limited`).
- [ ] 4.6 Add `frontend/src/{components,pages,hooks}/` per the repo's
      stated structure.

## 5. Frontend: ticker panel

- [ ] 5.1 Build the ticker panel component consuming `GET /tickers` via
      React Query — renders exactly the returned set, no free-text
      input for any other ticker.
- [ ] 5.2 Show per-ticker load status (not-loaded / loaded /
      features-computation-failed) using the status fields from `GET
      /tickers`.
- [ ] 5.3 Add a "load" action per ticker calling `POST
      /tickers/{ticker}/load` as a React Query mutation; on success,
      invalidate that ticker's `/prediction` and `/history` queries.
- [ ] 5.4 Surface load-in-progress and load-failure states distinctly.
      For this panel's traffic (only the 9 fixed, already-validated
      tickers — never malformed), the reachable failure status values
      from `/load` are `"rate_limited"` (show a retry-suggesting
      message) and `"no_data"` (show a distinct, non-retry-suggesting
      message — a previously-successful ticker temporarily having no
      data from vnstock is now handled gracefully rather than crashing;
      design.md Decision 7, `docs/KNOWN_ISSUES.md` closed entry).
      Separately, still handle a non-2xx/network-level failure with no
      parseable `status` field at all (a generic "something went wrong"
      message), for failures below the `status`-classification layer
      (e.g. the request itself timing out).
- [ ] 5.5 State in the panel's copy why only these tickers are offered
      (validated/backtested set — ties to design.md Decision 3 / Rule 6)
      rather than presenting the restriction unexplained.

## 6. Frontend: chart panel

- [ ] 6.1 Build the chart panel component consuming `GET
      /tickers/{ticker}/history` via React Query for the currently
      selected ticker.
- [ ] 6.2 Render OHLC candles only — no indicator overlay, no
      predicted-vs-actual series.
- [ ] 6.3 Handle the 404 (never-loaded) and loading states distinctly
      (e.g. empty-state prompting the user to load the ticker first).

## 7. Frontend: prediction display

- [ ] 7.1 Build the prediction display component consuming `GET
      /tickers/{ticker}/prediction` via React Query.
- [ ] 7.2 Implement the log-return-to-percentage conversion (`(e^x - 1) *
      100`) as a single shared utility function; the raw
      `predicted_log_return` value must not reach any render path
      unconverted (Rule 2).
- [ ] 7.3 Render four visually distinct states: `status: "ok"`
      (percentage + `as_of`), `status: "near_gap"`, `404`
      (not-loaded), `5xx` (feature computation failed) — no shared
      generic/blank state across more than one of these.

## 8. Frontend: AI insight placeholder panel

- [ ] 8.1 Add a placeholder panel in the AI-insight-panel layout position
      showing a static "coming in M6" / not-yet-available state.
- [ ] 8.2 Confirm no confidence score, sentiment proxy, or advice text is
      computed, fetched, or rendered anywhere on the page in this
      change (M5 does not call any M6 endpoint — none exists yet).

## 9. Frontend: dashboard assembly

- [ ] 9.1 Compose ticker panel, chart panel, prediction display, and the
      placeholder panel into the dashboard page/layout, wired so
      selecting a ticker in the panel drives the chart and prediction
      display for that same ticker.
- [ ] 9.2 Verify the load → invalidate → refetch flow end to end: loading
      a not-yet-loaded ticker updates its chart and prediction display
      without a manual page refresh.

## 10. Verification

- [ ] 10.1 `pytest backend/tests` passes, including the new tests from
      sections 1, 2, and 3.
- [ ] 10.2 `cd frontend && npm run test` passes for any frontend tests
      added alongside components 5-8.
- [ ] 10.3 Manual pass: for at least one ticker in each of the four
      prediction states (ok, near_gap, not-loaded, feature-failed —
      simulate the latter two via test data if not naturally available)
      confirm the dashboard shows the correct distinct UI state and no
      raw log return value appears anywhere, including dev tools/DOM
      inspection.
- [ ] 10.4 Manual pass: trigger (or simulate) a `rate_limited` load
      outcome and a `no_data` load outcome; confirm the panel shows two
      distinct messages (retry-suggesting for `rate_limited`,
      non-retry-suggesting for `no_data`) — neither collapsed into the
      other, nor into the catch-all/network-error case from task 5.4.
